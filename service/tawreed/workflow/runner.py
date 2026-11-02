"""The workflow at work on a background thread: each project moves through its fixed steps until it needs the
engineer.

The next step always follows from the records (next_step): read each file, propose the plan, place the items, then
ask to publish. Reading, planning and placing are AI steps, each run with only its own tools; asking to publish is
Tawreed's own. Stop takes effect between the AI's requests. An AI failure, a step that gets nowhere, or a declined
consent pauses the project with the reason; Continue (or answering a decision) carries on.
"""

import asyncio
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from pydantic_ai import Agent, UsageLimitExceeded, UsageLimits
from pydantic_ai.exceptions import ModelAPIError, ToolRetryError, UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, RetryPromptPart, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tawreed import decisions, ledger, packages, settings
from tawreed.ai import codex, connections, providers
from tawreed.core.db import now
from tawreed.projects import Project
from tawreed.sources import Source
from tawreed.workflow import prompts, tools
from tawreed.workflow.mcp_endpoint import Runs
from tawreed.workflow.records import StepRecord

log = logging.getLogger("tawreed.workflow")
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # Pydantic AI's advertisement, not wanted in the service log

REQUEST_TIMEOUT = 180.0  # seconds for one model request, so a stalled service can't hold the project
RETRIES = 2  # runs cut short by a passing AI failure that are tried again before the project pauses
RETRY_WAIT = 5.0  # seconds before the first retry; each further one waits longer
NO_PROGRESS = 2  # runs of a step in a row that change nothing before the project pauses


def chosen(home: Path) -> tuple[dict[str, Any], str] | None:
    """The connection and model Tawreed works with, if one is chosen and still there."""
    choice = settings.load(home)["ai"]
    connection = choice and connections.get(home, choice["connection_id"])
    return (connection, choice["model"]) if connection else None


@dataclass(frozen=True)
class Next:
    """The step a project is at: read (a file), plan, place, or publish (Tawreed asks the engineer)."""

    name: str
    source_id: str | None = None


def next_step(session: Session, project: Project) -> Next | None:
    """The project's next step, from its records; None while it waits for the engineer or has nothing to do."""
    waiting = {d.kind for d in decisions.waiting(session, project.id)}
    if "consent" in waiting:
        return None
    files = session.scalars(
        select(Source).where(Source.project_id == project.id, Source.active.is_(True)).order_by(Source.added_at)
    ).all()
    handled = {s.id: ledger.handled_pages(session, s.id) for s in files if s.status == "read"}
    for source in files:
        if source.status == "read" and {p.number for p in source.pages} - handled[source.id]:
            return Next("read", source.id)
    if any(s.status in ("added", "reading") for s in files):
        return None
    coverage = packages.coverage(session, project.id, decisions.waiting_items(session, project.id))
    if coverage.pending_files or not coverage.items or "plan" in waiting:
        return None
    if not packages.packages(session, project.id) or (project.redo or {}).get("step") == "plan":
        return Next("plan")
    if coverage.unplaced:
        return Next("place")
    if coverage.waiting or waiting:
        return None
    return None if asked_to_publish_since_change(session, project) else Next("publish")


def asked_to_publish_since_change(session: Session, project: Project) -> bool:
    latest = session.scalars(
        select(decisions.Decision)
        .where(
            decisions.Decision.project_id == project.id,
            decisions.Decision.kind == "publish",
            decisions.Decision.status != "withdrawn",
        )
        .order_by(decisions.Decision.created_at.desc())
        .limit(1)
    ).first()
    return bool(latest and latest.created_at >= project.updated_at)


def ask_to_publish(session: Session, project: Project) -> decisions.Decision:
    """Tawreed's publish card, once every item is placed and nothing waits: what it holds is computed on display."""
    return decisions.raise_decision(session, project.id, "publish", {}, "tawreed")


def withdraw_stale_publish(session: Session, project: Project) -> bool:
    """A publish card left up while the work changed so that it can't be published (an item to place again): it
    is withdrawn, and Tawreed asks again once the work is complete."""
    coverage = packages.coverage(session, project.id, decisions.waiting_items(session, project.id))
    stale = [] if coverage.complete and coverage.packages else decisions.waiting(session, project.id, "publish")
    for decision in stale:
        decisions.withdraw(decision)
    return bool(stale)


def remaining(session: Session, project: Project, step: Next) -> int:
    """What is left of a step's job, to tell whether a run got anywhere."""
    if step.name == "read":
        source = session.get(Source, step.source_id)
        return len({p.number for p in source.pages} - ledger.handled_pages(session, source.id))
    if step.name == "plan":
        return 0 if decisions.waiting(session, project.id, "plan") else 1
    return packages.coverage(session, project.id, decisions.waiting_items(session, project.id)).unplaced


class Worker:
    def __init__(
        self,
        home: Path,
        sessions: sessionmaker[Session],
        model: Callable[[], Model | None] | None = None,
        sees_images: Callable[[], bool] | None = None,
        runs: Runs | None = None,
        mcp_url: str | None = None,
        allowed: Callable[[], bool] = lambda: True,
    ):
        self.home = home
        self.allowed = allowed  # whether AI steps may run: signed in to QS Mind, within the offline lease
        self.sessions = sessions
        self.runs = runs or Runs()
        self.mcp_url = mcp_url  # where Codex reaches the step's tools; unknown when the service's port isn't
        self.model = model or self._chosen_model
        self.sees_images = sees_images or self._chosen_sees_images
        self._wake = threading.Event()
        self._closing = threading.Event()
        self._thread = threading.Thread(target=self._run, name="tawreed-workflow", daemon=True)
        self._stops: dict[str, threading.Event] = {}
        self._working: tuple[str, Next] | None = None
        self._failures: dict[str, int] = {}
        self._idle_runs: dict[str, int] = {}

    # The engineer's side ------------------------------------------------------------------------------------------

    def start(self) -> None:
        self._thread.start()
        self.wake()

    def close(self) -> None:
        self._closing.set()
        for stop in self._stops.values():
            stop.set()
        self._wake.set()
        self._thread.join(timeout=15)

    def wake(self) -> None:
        self._wake.set()

    def carry_on(self, project_id: str) -> None:
        """The engineer pressed Continue or answered: a stopped or paused project carries on."""
        self._stop(project_id).clear()
        self._failures.pop(project_id, None)
        self._idle_runs.pop(project_id, None)
        self.wake()

    def stop(self, project_id: str) -> None:
        """Stop the running step. The project stays stopped, even after a restart, until the engineer continues."""
        self._stop(project_id).set()
        with self.sessions() as session:
            project = session.get(Project, project_id)
            if project and not project.paused:
                project.paused, project.pause_reason = True, {"code": "stopped"}
                session.commit()

    def running(self, project_id: str) -> Next | None:
        """The step running on the project now, if any."""
        working = self._working
        return working[1] if working and working[0] == project_id else None

    def _stop(self, project_id: str) -> threading.Event:
        return self._stops.setdefault(project_id, threading.Event())

    # The work ---------------------------------------------------------------------------------------------------

    def _chosen_model(self) -> Model | None:
        found = chosen(self.home)
        if not found:
            return None
        connection, model = found
        return providers.build_model(connection["provider"], model, connection["api_key"], connection["base_url"])

    def _chosen_sees_images(self) -> bool:
        found = chosen(self.home)
        return bool(found and found[0]["checks"].get(found[1], {}).get("sees_images"))

    def _run(self) -> None:
        while not self._closing.is_set():
            self._wake.wait()
            self._wake.clear()
            try:
                asyncio.run(self.work())
            except Exception:
                log.exception("The workflow loop failed")

    async def work(self) -> None:
        """Run steps until no project has one to run."""
        busy = True
        while busy and not self._closing.is_set() and self.allowed():
            busy = False
            with self.sessions() as session:
                ids = list(session.scalars(select(Project.id).where(Project.paused.is_(False))))
            for project_id in ids:
                if self._stop(project_id).is_set() or self._closing.is_set():
                    continue
                busy = await self._work_on(project_id) or busy

    async def _work_on(self, project_id: str) -> bool:
        found = chosen(self.home)
        with self.sessions() as session:
            project = session.get(Project, project_id)
            if project and withdraw_stale_publish(session, project):
                session.commit()
            step = project and next_step(session, project)
            if step is None:
                return False
            if step.name == "publish":
                ask_to_publish(session, project)
                session.commit()
                return False
            if not found:
                return False
            if decisions.needs_consent(session, project_id, found[0]["id"]):
                decisions.ask_consent(session, project_id, found[0])
                session.commit()
                return False
            before = remaining(session, project, step)
            redo = project.redo if (project.redo or {}).get("step") == step.name else None
            if redo and redo.get("source_id") not in (None, step.source_id):
                redo = None
            note = redo and redo.get("note")
            if step.name == "read":
                prompt = prompts.read(session, session.get(Source, step.source_id), note)
            elif step.name == "plan":
                prompt = prompts.plan(session, project, note)
            else:
                prompt = prompts.place(session, project, note)
        codex_run = found[0]["provider"] == "codex"
        model = None if codex_run else self.model()
        if not codex_run and model is None:
            return False
        run = tools.Step(
            self.home, self.sessions, project_id, self._stop(project_id), self.sees_images(), step.name, step.source_id
        )
        self._working = (project_id, step)  # until what the run did is recorded, so it never looks finished early
        try:
            # Stop or delete may have come between choosing the step and marking it running: look again now
            if self._stop(project_id).is_set() or self._closing.is_set():
                return False
            with self.sessions() as session:
                if session.get(Project, project_id) is None:
                    return False
            if codex_run:
                ended = await self._codex_run(found[1], run, prompt)
            else:
                ended = await self._run_step(model, run, prompt)
            if ended not in ("done", "out_of_steps", "tool_failed"):
                return ended == "retry"
            with self.sessions() as session:
                project = session.get(Project, project_id)
                if ended == "done" and redo and project.redo == redo:
                    project.redo = None
                moved = remaining(session, project, step) < before
                idle = 0 if moved else self._idle_runs.get(project_id, 0) + 1
                self._idle_runs[project_id] = idle
                if idle >= NO_PROGRESS:
                    project.paused, project.pause_reason = True, {"code": "no_progress", "step": step.name}
                session.commit()
            return idle < NO_PROGRESS
        finally:
            self._working = None

    def _record(self, project_id: str, step: str, model: str) -> int:
        with self.sessions() as session:
            record = StepRecord(project_id=project_id, step=step, model=model[:200])
            session.add(record)
            session.commit()
            return record.id

    async def _codex_run(self, model: str | None, run: tools.Step, prompt: str) -> str:
        """A step through the Codex client: the step's tools, over Tawreed's MCP endpoint with this run's token."""
        if not self.mcp_url:
            return "failed"
        record_id = self._record(run.project_id, run.name, f"codex {model or ''}".strip())
        rules = prompts.rules(settings.load(self.home)["language"])
        token = self.runs.open(run)
        outcome = codex.Outcome(ended="failed", problem="codex_failed")
        try:
            outcome = await codex.run(model, rules + "\n\n" + prompt, self.mcp_url, token, run.stop)
        except Exception:
            log.exception("Codex couldn't run a step on %s", run.project_id)
        finally:
            self.runs.close(token)
            ended = {"done": "done", "stopped": "stopped", "out_of_time": "out_of_steps"}.get(outcome.ended)
            with self.sessions() as session:
                record = session.get(StepRecord, record_id)
                record.ended, record.note, record.calls = ended or "ai_failed", outcome.problem, outcome.calls
                record.ended_at = now()
                record.input_tokens, record.output_tokens = outcome.input_tokens, outcome.output_tokens
                session.commit()
        if outcome.ended == "failed":
            self._pause(run.project_id, "ai_failed", problem=outcome.problem or "codex_failed")
            return "failed"
        return ended or "failed"

    async def _run_step(self, model: Model, run: tools.Step, prompt: str) -> str:
        """done | out_of_steps | tool_failed | stopped | retry (a passing failure) | failed (the project paused)"""
        record_id = self._record(run.project_id, run.name, model.model_name)
        language = settings.load(self.home)["language"]
        trace = Trace()
        try:
            await run_step(model, run, prompts.rules(language), prompt, trace)
            self._failures.pop(run.project_id, None)
            return trace.ended
        except tools.Stopped:
            trace.ended = "stopped"
            return "stopped"
        except (ModelAPIError, httpx.TransportError, TimeoutError, OSError) as error:
            code, params = providers.explain(error)
            trace.ended, trace.note = "ai_failed", code
            failures = self._failures[run.project_id] = self._failures.get(run.project_id, 0) + 1
            if passing(error) and failures <= RETRIES:
                log.info("A step was cut short (%s); trying again", code)
                await asyncio.sleep(RETRY_WAIT * failures)
                return "retry"
            self._pause(run.project_id, "ai_failed", problem=code, **params)
            return "failed"
        except Exception as error:
            log.exception("A step on %s failed", run.project_id)
            trace.ended, trace.note = "failed", f"{type(error).__name__}: {str(error)[:500]}"
            self._pause(run.project_id, "step_failed")
            return "failed"
        finally:
            await providers.close_model(model)
            with self.sessions() as session:
                record = session.get(StepRecord, record_id)
                record.ended, record.note, record.calls = trace.ended, trace.note, trace.calls
                record.ended_at = now()
                record.requests = trace.usage.requests
                record.input_tokens, record.output_tokens = trace.usage.input_tokens, trace.usage.output_tokens
                session.commit()

    def _pause(self, project_id: str, code: str, **params: Any) -> None:
        with self.sessions() as session:
            project = session.get(Project, project_id)
            if project is None:
                return
            project.paused, project.pause_reason = True, {"code": code, **params}
            session.commit()


# One run of a step ------------------------------------------------------------------------------------------------


@dataclass
class Trace:
    """What one run did, filled in while it runs, so it is there however the run ends."""

    ended: str = "done"
    note: str | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    usage: RunUsage = field(default_factory=RunUsage)


def calls_in(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    """Each tool call in the run, with the reason when Tawreed sent it back."""
    sent_back = {
        p.tool_call_id: str(p.content)[:300]
        for m in messages
        for p in m.parts
        if isinstance(p, RetryPromptPart) and p.tool_name
    }
    return [
        {"tool": p.tool_name, "sent_back": sent_back.get(p.tool_call_id)}
        for m in messages
        for p in m.parts
        if isinstance(p, ToolCallPart)
    ]


def passing(error: BaseException) -> bool:
    """A failure that usually clears on its own: a timeout, a dropped connection, rate limiting, a server error."""
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    if isinstance(error, httpx.TransportError | TimeoutError | ConnectionError):
        return True
    cause = type(error.__cause__).__name__.lower() if error.__cause__ else ""
    return "timeout" in cause or "connect" in cause


async def run_step(model: Model, run: tools.Step, rules: str, prompt: str, trace: Trace) -> None:
    agent = Agent(
        model,
        deps_type=tools.Step,
        instructions=rules,
        tools=tools.STEP_TOOLS[run.name],
        retries=2,
        model_settings=ModelSettings(timeout=REQUEST_TIMEOUT),
    )
    limits = UsageLimits(request_limit=prompts.STEP_LIMITS[run.name])
    async with agent.iter(prompt, deps=run, usage_limits=limits) as going:
        try:
            asked = time.monotonic()
            async for node in going:
                if run.stop.is_set():
                    raise tools.Stopped()
                if Agent.is_model_request_node(node):
                    asked = time.monotonic()
                    # Streamed: some services drop a long answer that arrives in one piece after a quiet minute.
                    async with node.stream(going.ctx) as answer:
                        async for _event in answer:
                            if run.stop.is_set():
                                raise tools.Stopped()
                elif Agent.is_call_tools_node(node):
                    calls = [p.tool_name for p in node.model_response.parts if isinstance(p, ToolCallPart)]
                    log.info("Answered in %.1f s, calling %s", time.monotonic() - asked, calls)
                    if not calls:
                        return  # the step's job is done, as far as the model is concerned
        except UsageLimitExceeded:
            trace.ended = "out_of_steps"
        except (UnexpectedModelBehavior, ToolRetryError) as error:
            # A reply the model couldn't get right ends this run, not the project's work.
            log.info("A step ended early: %s", str(error)[:300])
            trace.ended, trace.note = "tool_failed", str(error)[:500]
        finally:
            trace.calls, trace.usage = calls_in(going.new_messages()), going.usage
