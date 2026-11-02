"""QS Mind connect: sign a desktop app in to the QS Mind account (auth.qsmind.app).

The app is a native public OpenID Connect client (no secret) of the QS Mind account service, as the service's
`docs/contract.md` and `src/clients.ts` describe it:

1. Discovery: `{issuer}/.well-known/openid-configuration` names every endpoint below.
2. Loopback sign-in (RFC 8252): a listener on 127.0.0.1 at a free port takes the browser's one redirect back to
   `http://127.0.0.1:<port>/callback` (registered as `http://127.0.0.1/callback`; any loopback port matches). The
   authorization request carries PKCE (S256), `state`, `nonce` and `scope=openid profile email offline_access`
   (refresh tokens come only with `offline_access`).
3. The code is exchanged at the token endpoint with the PKCE verifier.
4. The ID token is checked (RS256, key by `kid` from the JWKS, issuer, audience, expiry, nonce), then user info gives
   the email and name. A `plan` claim, in either, is the account's plan.
5. Device sign-in (RFC 8628), the fallback: a short code the person approves at the account's device page.
6. Refresh with `grant_type=refresh_token`. Refresh tokens rotate: keep the new one.
7. Sign out revokes the refresh token.

This module knows nothing of the app around it: standard library, httpx and PyJWT only, so another QS Mind desktop
app with a Python service can copy it whole. The app keeps the tokens (in the OS keychain) and decides what a
refusal means."""

import base64
import hashlib
import html
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import jwt

ISSUER = "https://auth.qsmind.app"
SCOPE = "openid profile email offline_access"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
SIGN_IN_SECONDS = 10 * 60  # how long a browser sign-in waits for the redirect back


class Refused(Exception):
    """The account service answered no, with an OAuth error code: `invalid_grant` (a refresh token that is revoked,
    expired or for a disabled account), `access_denied`, `expired_token`, ..."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Failed(Exception):
    """The request could not be completed: no connection (`offline`), a server error, or an answer that doesn't hold
    up (an ID token that doesn't verify). Not a refusal: trying again later may work."""

    def __init__(self, reason: str, offline: bool = False):
        super().__init__(reason)
        self.offline = offline


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str | None
    profile: dict[str, Any]  # sub, email, name, plan (None when the account service sends none)


@dataclass(frozen=True)
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None
    expires_in: int
    interval: int


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


class Client:
    """One app's connection to the account service. Thread-safe enough for one app: discovery and keys are cached."""

    def __init__(self, client_id: str, issuer: str = ISSUER, http: httpx.Client | None = None):
        self.client_id = client_id
        self.issuer = issuer.rstrip("/")
        self.http = http or httpx.Client(timeout=TIMEOUT)
        self._metadata: dict[str, Any] | None = None
        self._keys: dict[str, Any] = {}

    # Plumbing ------------------------------------------------------------------------------------------------------

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self.http.request(method, url, **kwargs)
        except httpx.TransportError as error:
            raise Failed(f"{type(error).__name__}: {error}", offline=True) from error
        if response.status_code >= 500:
            raise Failed(f"{url} answered {response.status_code}")
        return response

    def metadata(self) -> dict[str, Any]:
        if self._metadata is None:
            response = self._request("GET", f"{self.issuer}/.well-known/openid-configuration")
            data = response.json() if response.is_success else None
            if not isinstance(data, dict) or data.get("issuer", "").rstrip("/") != self.issuer:
                raise Failed("discovery did not name this issuer")
            self._metadata = data
        return self._metadata

    def _endpoint(self, name: str) -> str:
        url = self.metadata().get(name)
        if not url:
            raise Failed(f"the account service publishes no {name}")
        return url

    def _token(self, form: dict[str, str]) -> dict[str, Any]:
        response = self._request("POST", self._endpoint("token_endpoint"), data={**form, "client_id": self.client_id})
        try:
            data = response.json()
        except ValueError as error:
            raise Failed(f"token endpoint answered {response.status_code} without JSON") from error
        if response.is_success and data.get("access_token"):
            return data
        if isinstance(data, dict) and data.get("error"):
            raise Refused(str(data["error"]))
        raise Failed(f"token endpoint answered {response.status_code}")

    def _key(self, kid: str | None) -> Any:
        if kid not in self._keys:  # keys rotate: an unknown kid means the set changed, so fetch it again once
            response = self._request("GET", self._endpoint("jwks_uri"))
            try:
                found = jwt.PyJWKSet.from_dict(response.json())
            except (ValueError, jwt.PyJWTError) as error:
                raise Failed("the key set can't be read") from error
            self._keys = {key.key_id: key for key in found.keys}
        if kid not in self._keys:
            raise Failed(f"no key {kid!r} in the key set")
        return self._keys[kid]

    def _claims(self, id_token: str, nonce: str | None) -> dict[str, Any]:
        try:
            key = self._key(jwt.get_unverified_header(id_token).get("kid"))
            claims = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=self.issuer,
                leeway=60,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
        except jwt.PyJWTError as error:
            raise Failed(f"the ID token does not verify: {error}") from error
        if nonce is not None and not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise Failed("the ID token is for another sign-in (nonce)")
        return claims

    def _finish(self, answer: dict[str, Any], nonce: str | None, sub: str | None = None) -> Tokens:
        """Tokens from a token answer: the ID token checked, the profile from it and user info."""
        claims = self._claims(answer["id_token"], nonce) if answer.get("id_token") else {}
        if not claims and sub is None:
            raise Failed("no ID token in the answer")
        response = self._request(
            "GET", self._endpoint("userinfo_endpoint"), headers={"Authorization": f"Bearer {answer['access_token']}"}
        )
        info = response.json() if response.is_success else None
        if not isinstance(info, dict):
            raise Failed(f"user info answered {response.status_code}")
        expected = claims.get("sub") or sub
        if info.get("sub") != expected or (sub is not None and expected != sub):
            raise Refused("wrong_account")
        profile = {
            "sub": expected,
            "email": info.get("email") or claims.get("email"),
            "name": info.get("name") or claims.get("name"),
            "plan": claims.get("plan") or info.get("plan"),
        }
        return Tokens(answer["access_token"], answer.get("refresh_token"), profile)

    # Sign-in, refresh, sign-out -----------------------------------------------------------------------------------

    def browser_sign_in(
        self, locale: str, done: Callable[[Tokens | None, Exception | None], None], app_name: str = ""
    ) -> "BrowserSignIn":
        return BrowserSignIn(self, locale, done, app_name)

    def exchange(self, code: str, redirect_uri: str, verifier: str, nonce: str) -> Tokens:
        answer = self._token(
            {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "code_verifier": verifier}
        )
        return self._finish(answer, nonce)

    def refresh(self, refresh_token: str, sub: str) -> Tokens:
        """New tokens for the same account. A rotated refresh token is in the answer; keep it in place of the old."""
        answer = self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})
        return self._finish(answer, None, sub)

    def revoke(self, refresh_token: str) -> None:
        self._request(
            "POST",
            self._endpoint("revocation_endpoint"),
            data={"token": refresh_token, "token_type_hint": "refresh_token", "client_id": self.client_id},
        )

    def device_code(self) -> DeviceCode:
        response = self._request(
            "POST", self._endpoint("device_authorization_endpoint"), data={"client_id": self.client_id, "scope": SCOPE}
        )
        data = response.json() if response.is_success else None
        if not isinstance(data, dict) or not data.get("device_code"):
            raise Failed(f"device authorization answered {response.status_code}")
        return DeviceCode(
            data["device_code"],
            data["user_code"],
            data["verification_uri"],
            data.get("verification_uri_complete"),
            int(data.get("expires_in", 600)),
            int(data.get("interval", 5)),
        )

    def wait_for_device(self, device: DeviceCode, stopped: threading.Event) -> Tokens | None:
        """Ask at the interval until the person approves (the tokens), refuses or lets the code expire (Refused), or
        `stopped` is set (None)."""
        interval, waited = max(device.interval, 1), 0
        while waited < device.expires_in:
            if stopped.wait(interval):
                return None
            waited += interval
            try:
                return self._finish(self._token({"grant_type": DEVICE_GRANT, "device_code": device.device_code}), None)
            except Refused as refusal:
                if refusal.code == "slow_down":
                    interval += 5
                elif refusal.code != "authorization_pending":
                    raise
        raise Refused("expired_token")


_PAGE = {
    "en": ("Signed in", "You are signed in. You can close this tab and go back to {app}."),
    "ar": ("تم تسجيل الدخول", "تم تسجيل الدخول. يمكنك إغلاق هذه الصفحة والعودة إلى {app}."),
}
_PAGE_FAILED = {
    "en": ("Sign-in did not finish", "Sign-in did not finish. Go back to {app} and try again."),
    "ar": ("لم يكتمل تسجيل الدخول", "لم يكتمل تسجيل الدخول. ارجع إلى {app} وحاول مرة أخرى."),
}


class BrowserSignIn:
    """One sign-in through the system browser: the authorization address to open, and a listener on 127.0.0.1 for
    the one redirect back. `done` is called once, with the tokens or the reason it failed (Refused("expired_token")
    when nobody came back in time); not at all after `cancel`."""

    def __init__(
        self,
        client: Client,
        locale: str,
        done: Callable[[Tokens | None, Exception | None], None],
        app_name: str = "",
    ):
        self.client, self.locale, self._done, self.app_name = client, locale, done, app_name
        self.state, self.nonce, self.verifier = (secrets.token_urlsafe(32) for _ in range(3))
        self._answered = threading.Event()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.redirect_uri = f"http://127.0.0.1:{self.server.server_address[1]}/callback"
        query = {
            "response_type": "code",
            "client_id": client.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": SCOPE,
            "state": self.state,
            "nonce": self.nonce,
            "code_challenge": _challenge(self.verifier),
            "code_challenge_method": "S256",
            "ui_locales": locale,
        }
        self.url = f"{client._endpoint('authorization_endpoint')}?{urlencode(query)}"
        threading.Thread(target=self.server.serve_forever, name="qsmind-sign-in", daemon=True).start()
        self._timer = threading.Timer(SIGN_IN_SECONDS, self._expire)
        self._timer.daemon = True
        self._timer.start()

    def cancel(self) -> None:
        if not self._answered.is_set():
            self._answered.set()
            self._close()

    def _expire(self) -> None:
        if not self._answered.is_set():
            self._answered.set()
            self._close()
            self._done(None, Refused("expired_token"))

    def _close(self) -> None:
        self._timer.cancel()
        threading.Thread(target=self.server.shutdown, daemon=True).start()  # not from the handler's own thread
        closing = threading.Timer(1, self.server.server_close)
        closing.daemon = True
        closing.start()

    def _callback(self, query: dict[str, list[str]]) -> tuple[int, bool]:
        """What the redirect back carries: the status to answer and whether sign-in finished."""
        state = (query.get("state") or [""])[0]
        if not secrets.compare_digest(state, self.state) or self._answered.is_set():
            return 400, False  # not this sign-in's redirect: ignore it and keep waiting
        self._answered.set()
        tokens: Tokens | None = None
        problem: Exception | None = None
        try:
            if query.get("error"):
                raise Refused(query["error"][0])
            code = (query.get("code") or [""])[0]
            if not code:
                raise Failed("no code in the redirect")
            tokens = self.client.exchange(code, self.redirect_uri, self.verifier, self.nonce)
        except (Refused, Failed) as error:
            problem = error
        finally:
            self._close()
        self._done(tokens, problem)
        return 200, problem is None

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        sign_in = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (the standard library's name)
                url = urlparse(self.path)
                if url.path != "/callback":
                    self.send_error(404)  # a favicon or a stray request: nothing to do with the sign-in
                    return
                status, ok = sign_in._callback(parse_qs(url.query))
                self._answer(status, ok)

            def _answer(self, status: int, ok: bool) -> None:
                language = "ar" if sign_in.locale == "ar" else "en"
                title, text = (_PAGE if ok else _PAGE_FAILED)[language]
                text = html.escape(text.format(app=sign_in.app_name or "the app"))
                body = (
                    f'<!doctype html><html lang="{language}" dir="{"rtl" if language == "ar" else "ltr"}"><head>'
                    f'<meta charset="utf-8"><title>{html.escape(title)}</title></head>'
                    f'<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem">'
                    f"<p>{text}</p></body></html>"
                ).encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:  # the redirect carries the code: never log it
                pass

        return Handler
