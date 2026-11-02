"""The engineer's QS Mind account on this computer: signed in, the offline lease, and what happens when it ends.

- The refresh token is in the OS keychain (`core.keychain`), never in ~/.tawreed. ~/.tawreed/account.json holds
  only who is signed in and when the last refresh succeeded.
- Tawreed refreshes at most once an hour while the interface asks for the account (five minutes after a failed try),
  in the background: the answer is the state before that refresh.
- The lease: Tawreed works for LEASE_DAYS after the last successful refresh, online or not. After that it is
  read-only (`writable()` is False: no changes, no AI steps) until a refresh succeeds. Nothing is deleted.
- A refusal from the account service (signed out everywhere, account disabled, token expired) signs out here.
  Projects stay for the next sign-in.

The protocol itself is in `account.qsmind`; see docs/2026-11-02-qsmind-sign-in.md."""

import logging
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tawreed.account import qsmind
from tawreed.ai.connections import make_private
from tawreed.core import env, jsonfile, keychain

log = logging.getLogger("tawreed.account")

LEASE_DAYS = 14  # Tawreed works offline this long after the last successful refresh
LEASE = timedelta(days=LEASE_DAYS)
REFRESH_EVERY = timedelta(hours=1)
RETRY_AFTER = timedelta(minutes=5)
REFRESH_TOKEN = "qsmind-refresh-token"  # its name in the keychain
# Given by auth.qsmind.app when Tawreed is registered as a native client; TAWREED_AUTH_CLIENT_ID overrides it.
CLIENT_ID = ""
APP_NAME = {"en": "Tawreed", "ar": "توريد"}


class Unavailable(Exception):
    """Sign-in can't start: `code` says why (sign_in_unavailable, auth_unreachable, auth_failed)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _problem(error: Exception) -> str:
    """A failed sign-in, as the code the interface explains."""
    if isinstance(error, keychain.Unavailable):
        return "keychain_unavailable"
    if isinstance(error, qsmind.Refused):
        return {"access_denied": "sign_in_denied", "expired_token": "sign_in_expired"}.get(error.code, "sign_in_failed")
    if isinstance(error, qsmind.Failed) and error.offline:
        return "auth_unreachable"
    return "sign_in_failed"


class Account:
    def __init__(self, home: Path, on_change: Callable[[], None] = lambda: None, now=lambda: datetime.now(UTC)):
        self.home = home
        self.on_change = on_change  # called when Tawreed may have become writable again (wakes the AI steps)
        self.now = now
        self._lock = threading.RLock()
        self._client: qsmind.Client | None = None
        self._pending: dict[str, Any] | None = None  # the sign-in under way, as the interface shows it
        self._cancel: Callable[[], None] | None = None
        self._problem: str | None = None  # why the last sign-in failed
        self._failed_at: datetime | None = None  # the last refresh that failed (offline), since the last success
        self._refresh_token: str | None = None  # the newest one, should the keychain have refused it
        self._refreshing = False

    # What the interface and the service ask -------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        self._refresh_if_due()
        with self._lock:
            record = self._record()
            return {
                "state": self._state(record),
                "email": record and record.get("email"),
                "name": record and record.get("name"),
                "plan": record and record.get("plan"),
                "lease_ends_at": record and (self._refreshed_at(record) + LEASE).isoformat(),
                "pending": self._pending,
                "problem": self._problem,
            }

    def signed_in(self) -> bool:
        return self._record() is not None

    def writable(self) -> bool:
        """Whether the engineer can change projects and the AI steps can run: signed in, within the lease."""
        return self._state(self._record()) in ("active", "offline")

    # Sign-in --------------------------------------------------------------------------------------------------

    def sign_in(self, locale: str) -> dict[str, Any]:
        """Open the system browser at the QS Mind account; the redirect back finishes the sign-in."""
        with self._lock:
            self._stop_pending()
            try:
                flow = self.client().browser_sign_in(locale, self._finished, APP_NAME.get(locale, APP_NAME["en"]))
            except qsmind.Failed as error:
                raise Unavailable("auth_unreachable" if error.offline else "auth_failed") from error
            self._cancel = flow.cancel
            self._pending = {"method": "browser", "url": flow.url, "user_code": None}
        env.open_url(flow.url)
        return self.status()

    def sign_in_with_code(self, locale: str) -> dict[str, Any]:
        """The fallback: a code the engineer approves at the account's device page, on any device."""
        with self._lock:
            self._stop_pending()
            try:
                device = self.client().device_code()
            except qsmind.Failed as error:
                raise Unavailable("auth_unreachable" if error.offline else "auth_failed") from error
            stopped = threading.Event()
            url = device.verification_uri_complete or device.verification_uri
            self._cancel = stopped.set
            self._pending = {"method": "code", "url": url, "user_code": device.user_code}

        def wait() -> None:
            try:
                tokens = self.client().wait_for_device(device, stopped)
            except (qsmind.Refused, qsmind.Failed) as error:
                tokens, problem = None, error
            else:
                problem = None
            if not stopped.is_set():
                self._finished(tokens, problem)

        threading.Thread(target=wait, name="qsmind-device", daemon=True).start()
        env.open_url(url)
        return self.status()

    def cancel(self) -> None:
        with self._lock:
            self._stop_pending()

    def sign_out(self) -> None:
        """Sign out here: the refresh token is revoked when the account service can be reached, and forgotten here
        either way. Projects stay."""
        with self._lock:
            self._stop_pending()
            token = self._refresh_token or self._keychain_token()
            if token and self._record():
                try:
                    self.client().revoke(token)
                except qsmind.Failed as error:
                    log.info("The refresh token could not be revoked (%s); it is forgotten here", error)
            self._end()

    # Inside ---------------------------------------------------------------------------------------------------

    def client(self) -> qsmind.Client:
        if self._client is None:
            client_id = os.environ.get("TAWREED_AUTH_CLIENT_ID") or CLIENT_ID
            if not client_id:
                raise Unavailable("sign_in_unavailable")
            self._client = qsmind.Client(client_id, os.environ.get("TAWREED_AUTH_ISSUER") or qsmind.ISSUER)
        return self._client

    def _path(self) -> Path:
        return self.home / "account.json"

    def _record(self) -> dict[str, Any] | None:
        record = jsonfile.read(self._path(), {})
        return record if record.get("sub") and record.get("refreshed_at") else None

    def _refreshed_at(self, record: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(record["refreshed_at"])

    def _state(self, record: dict[str, Any] | None) -> str:
        if record is None:
            return "signed_out"
        refreshed = self._refreshed_at(record)
        if self.now() >= refreshed + LEASE:
            return "expired"
        return "offline" if self._failed_at and self._failed_at > refreshed else "active"

    def _stop_pending(self) -> None:
        if self._cancel:
            self._cancel()
        self._cancel, self._pending, self._problem = None, None, None

    def _keychain_token(self) -> str | None:
        try:
            return keychain.read(self.home, REFRESH_TOKEN)
        except keychain.Unavailable as error:
            log.warning("The keychain can't be read: %s", error)
            return None

    def _finished(self, tokens: qsmind.Tokens | None, problem: Exception | None) -> None:
        """A sign-in ended: keep the account, or say why it failed."""
        with self._lock:
            self._cancel, self._pending = None, None
            if tokens is not None and not tokens.refresh_token:
                problem = qsmind.Failed("no refresh token: was offline_access granted?")
            if tokens is not None and problem is None:
                try:
                    keychain.write(self.home, REFRESH_TOKEN, tokens.refresh_token)
                except keychain.Unavailable as error:
                    problem = error
            if problem is not None:
                log.warning("Sign-in did not finish: %s", problem)
                self._problem = _problem(problem)
                return
            self._refresh_token, self._failed_at, self._problem = tokens.refresh_token, None, None
            self._save(tokens.profile)
            log.info("Signed in to QS Mind")
        self.on_change()

    def _save(self, profile: dict[str, Any]) -> None:
        record = {**profile, "refreshed_at": self.now().isoformat()}

        def replace(data: dict[str, Any]) -> None:
            data.clear()
            data.update(record)

        jsonfile.update(self._path(), {}, replace)
        make_private(self._path())

    def _end(self) -> None:
        self._refresh_token, self._failed_at = None, None
        try:
            keychain.delete(self.home, REFRESH_TOKEN)
        except keychain.Unavailable as error:
            log.warning("The refresh token could not be removed from the keychain: %s", error)
        self._path().unlink(missing_ok=True)

    def _refresh_if_due(self) -> None:
        with self._lock:
            record = self._record()
            now = self.now()
            if (
                record is None
                or self._refreshing
                or now - self._refreshed_at(record) < REFRESH_EVERY
                or (self._failed_at is not None and now - self._failed_at < RETRY_AFTER)
            ):
                return
            self._refreshing = True

        def refresh() -> None:
            try:
                self._refresh(record)
            finally:
                with self._lock:
                    self._refreshing = False

        # In the background, so asking for the account never waits on the network; the next ask sees the result.
        threading.Thread(target=refresh, name="qsmind-refresh", daemon=True).start()

    def _refresh(self, record: dict[str, Any]) -> None:
        token = self._refresh_token
        if token is None:
            try:
                token = keychain.read(self.home, REFRESH_TOKEN)
            except keychain.Unavailable as error:
                log.warning("The keychain can't be read, so the account isn't refreshed: %s", error)
                self._failed_at = self.now()
                return
        if not token:
            log.warning("The refresh token is gone from the keychain: signed out")
            with self._lock:
                self._end()
            return
        try:
            tokens = self.client().refresh(token, record["sub"])
        except qsmind.Refused as refusal:
            log.info("QS Mind refused the refresh (%s): signed out", refusal.code)
            with self._lock:
                self._end()
            return
        except (qsmind.Failed, Unavailable) as error:
            log.info("The account could not be refreshed (%s); the lease counts on", error)
            self._failed_at = self.now()
            return
        with self._lock:
            if tokens.refresh_token and tokens.refresh_token != token:
                self._refresh_token = tokens.refresh_token
                try:
                    keychain.write(self.home, REFRESH_TOKEN, tokens.refresh_token)
                except keychain.Unavailable as error:
                    log.warning("The new refresh token could not be kept in the keychain: %s", error)
            self._failed_at = None
            self._save(tokens.profile)
        self.on_change()
