# Architecture

## Shape: a modular monolith

One developer, a local-first desktop app. Tawreed is one Python service with clear domain modules, one React
interface and a thin desktop shell — the same shape as its sibling app Quantix. No microservices, plugin system or
compatibility layers.

```
ui/        React + Vite + TypeScript, Tailwind + shadcn/ui, TanStack Query; API types generated from OpenAPI
desktop/   Tauri 2 shell: the window; installed, it also starts the service and forwards to it. No domain logic.
service/   Python 3.12, FastAPI, SQLAlchemy 2 + Alembic (SQLite), Pydantic AI
  tawreed/
    core/        data home ~/.tawreed, database, atomic JSON files, launch token, the OS keychain
    account/     sign in with QS Mind (qsmind.py, the protocol, copyable), the session and the offline lease
    ai/          connections and keys, the five API providers, the model check, subscription clients
    projects/    projects and consent records
    sources/     import, hashing, readers (Excel, CSV, ODS, PDF text with positions, page images), overlap
    ledger/      the immutable item ledger and the extractor that applies a proposed layout
    packages/    package plans, packages, assignments, checked operations, rule memory
    decisions/   gates: consent, overlap, plan, uncertain assignment, publish
    workflow/    the fixed steps: runner, step tools and prompts, the MCP endpoint the Codex client uses
    publish/     workbook builders, coverage and totals checks, atomic revisions with a manifest
    api/         HTTP routes per module
  tests/
docs/
```

**Why:**

- One stack across Tawreed and Quantix: the same patterns, tools and habits.
- Pydantic AI covers all five API providers and lets tests drive the real runtime with a scripted model.
- Python has the strongest Excel, PDF and Arabic text tooling.
- SQLite through SQLAlchemy keeps the data in one local file with real transactions.

Each domain module owns its models and its service functions; the workflow's step tools call them.

## Boundaries

- The UI talks only to the HTTP API on loopback. Each service launch gets a fresh bearer token. In development the
  Vite server starts the service on a free port and forwards `/api` with the token, so the browser preview and the
  desktop window use the same path and the UI never holds the token or a key.
- AI connections are in `~/.tawreed/connections.json`, locked to the current user; their keys are in the OS keychain
  (`core/keychain.py`, through `keyring`). The service never returns a key, and keys are redacted from logs and
  prompts.
- The QS Mind account: the service holds the session (`account/`): loopback PKCE sign-in in the system browser, a
  device code as the fallback, the refresh token in the OS keychain, an offline lease of 14 days. Past the lease,
  changes to projects answer `403 read_only` and the workflow holds its AI steps. See
  `docs/2026-11-02-qsmind-sign-in.md`.
- `TAWREED_HOME` points the service at another data folder, for tests and scratch runs.
- Long work runs on background threads from records in the database: files waiting to be read, and the runs of
  the workflow's steps, each recorded as it starts and ends. After a restart, a file left half-read is read again
  and the next step follows from the records. The interface asks for the project's state every second or so while a
  step runs;
  it is a local service, so polling is simpler than a push channel and costs nothing noticeable.
- Database migrations run with SQLite's foreign keys off (SQLite changes a table by rebuilding it, and dropping
  the old table would otherwise delete every row that refers to it), then the references are checked before the
  migration is kept.

## The workflow

- **Fixed steps.** A background worker moves each project through Read (one run per file), Plan and Place, then
  Tawreed asks to publish. The next step always follows from the project's records (`workflow.runner.next_step`);
  nothing is carried as chat history.
- **Scoped runs.** Each run of a step gets a short fixed prompt and only that step's tools (`STEP_TOOLS`): a Read
  run only its own file. The AI can't write to the engineer, ask questions or publish.
- **Structure from AI, values from Tawreed.** The AI proposes layouts, plans and assignments. Tawreed extracts
  values, validates proposals and computes every count and total. The AI never writes an item field or a number.
- **Gates.** Nothing that changes the project's commitments happens until the engineer answers through the API.
  Tawreed raises consent, overlap and publish; the AI's step tools raise the plan and uncertain items.
- **The engineer's word.** Their own layouts and placements are final: the AI's tools refuse to change them. A Redo
  keeps the engineer's note on the project until that step has run; the note reaches the model fenced as their words.
- **Untrusted documents.** BOQ text is passed to the model as delimited data and is never treated as instructions.
- **Stop** ends the running step. An AI failure, a step that gets nowhere twice, or a declined consent pauses the
  project with a reason, as a code; Continue carries on.

### Providers

- API keys: Pydantic AI runs the tool loop against the chosen model.
- ChatGPT subscription: Tawreed runs the official Codex client (`codex exec`) for each run of a step, in an empty folder with
  a read-only sandbox, without the engineer's Codex settings, rules or MCP servers, and with its own shell, command,
  file, image, sub-agent, app, plugin, browser and web tools off. The service serves the same tool functions over
  MCP at `/mcp`; each run gets a one-time token, passed to Codex in an environment variable, and the endpoint
  answers nothing else and refuses any tool outside the run's step. The endpoint is marked required (Codex waits for it, so its tools are searchable from the
  start) and its tools approved (so they run without a prompt no one would answer). The prompt goes in on
  standard input. A model check runs the same way against `/mcp-check`.

## The installed app

- The service is frozen with PyInstaller into one folder and shipped as a resource of the NSIS installer (installed
  for the current user, no administrator rights). The interface is embedded in the Tauri executable.
- On start the desktop app picks a free loopback port and a fresh token, starts the service hidden with both, and
  answers the interface's requests to its own `api` scheme (`http://api.localhost` on Windows) by forwarding them
  to the service with the token. As in development, the page never holds the token.
- The app holds the service's standard input open; the service stops when it closes, so it can't outlive the app,
  even after a crash.
- Updates are signed and the engineer starts them. The desktop app answers `/desktop/update` on the `api` scheme
  itself: it reads the feed at the one address in `desktop/tauri.release.conf.json`, and installs only an installer
  whose signature matches the public key built into the app. See `docs/2026-10-10-updater-and-installer.md`.

## Fonts

- **Kumbh Sans** (English, the QS Mind site's typeface) is open source (SIL Open Font License) and bundled with the
  interface from the `@fontsource-variable/kumbh-sans` package. Headings use Light (300), body text Regular (400), labels SemiBold (600).
- **Thmanyah Sans** (all Arabic; headings are Light with its swash letters, `swsh`) is licensed for use
  inside a compiled or packaged product only. Its files must never be committed, uploaded or hosted anywhere,
  including GitHub, and must not sit loose where users can copy them. They are kept locally in the gitignored
  `ui/src/fonts/thmanyah/` and reach users only inside the Tauri executable, which embeds the built interface. The
  release interface is therefore served from Tauri's embedded assets, not from a folder on disk. Builds without the files (CI) fall back to the system Arabic font; release builds that include
  Thmanyah are made on the engineer's machine.

## Publishing

Workbooks are built with openpyxl into a staging folder, checked (every active item exactly once, totals reconcile)
and re-opened, then the folder is renamed into place as `Rev NN` with a manifest of file digests.

## Testing

Service tests use pytest; the workflow is tested with a scripted model at the provider boundary (Pydantic AI
`FunctionModel`), so the real runner, step tools, gates and database are exercised. Generated workbooks are re-opened
and asserted. UI tests use Vitest and Testing Library. `npm run verify` runs tests, typecheck, Ruff and Clippy
before every push; CI runs the same checks when started by hand and fails if the API types drift from the service.
