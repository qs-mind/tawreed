"""A stand-in for the QS Mind account service (auth.qsmind.app) on loopback, for tests: discovery, keys, authorize,
token (code with PKCE, rotating refresh tokens, device grant), user info, revocation and device authorization. It
behaves as the real one does for a native client, so the real sign-in code runs against it; no test reaches the real
service."""

import base64
import hashlib
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

CLIENT_ID = "tawreed-test-client"


class FakeOIDC:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "key-1"
        self.user = {"sub": "0b9f5a7e-1111-4222-8333-944445555666", "email": "eng@example.test", "name": "Mona Adel"}
        self.plan: str | None = None  # the `plan` claim, when set
        self.deny = False  # the person refuses on the consent page
        self.down = False  # every request answers 503
        self.codes: dict[str, dict[str, Any]] = {}
        self.refresh_tokens: dict[str, str] = {}  # live token -> sub
        self.access_tokens: dict[str, str] = {}
        self.devices: dict[str, dict[str, Any]] = {}  # device_code -> {user_code, approved}
        self.revoked: list[str] = []
        self.authorize_queries: list[dict[str, str]] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.issuer = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    # What a test does as the person -------------------------------------------------------------------------

    def approve_device(self, user_code: str) -> None:
        for device in self.devices.values():
            if device["user_code"] == user_code:
                device["approved"] = True

    def revoke_everything(self) -> None:
        """Sign out everywhere: every refresh token stops working."""
        self.refresh_tokens.clear()

    # Tokens -------------------------------------------------------------------------------------------------

    def id_token(self, nonce: str | None = None, **changes: Any) -> str:
        now = int(time.time())
        claims = {"iss": self.issuer, "aud": CLIENT_ID, "sub": self.user["sub"], "iat": now, "exp": now + 3600}
        if nonce:
            claims["nonce"] = nonce
        if self.plan:
            claims["plan"] = self.plan
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": self.kid})

    def _tokens(self, nonce: str | None = None) -> dict[str, Any]:
        access, refresh = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
        self.access_tokens[access] = self.user["sub"]
        self.refresh_tokens[refresh] = self.user["sub"]
        return {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": refresh,
            "id_token": self.id_token(nonce),
            "scope": "openid profile email offline_access",
        }

    def _token(self, form: dict[str, str]) -> tuple[int, dict[str, Any]]:
        if form.get("client_id") != CLIENT_ID:
            return 401, {"error": "invalid_client"}
        grant = form.get("grant_type")
        if grant == "authorization_code":
            request = self.codes.pop(form.get("code", ""), None)
            if request is None or request["redirect_uri"] != form.get("redirect_uri"):
                return 400, {"error": "invalid_grant"}
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(form.get("code_verifier", "").encode()).digest())
                .rstrip(b"=")
                .decode()
            )
            if challenge != request["code_challenge"]:
                return 400, {"error": "invalid_grant", "error_description": "PKCE"}
            return 200, self._tokens(request["nonce"])
        if grant == "refresh_token":
            if self.refresh_tokens.pop(form.get("refresh_token", ""), None) is None:
                return 400, {"error": "invalid_grant"}
            answer = self._tokens()  # rotated: the old token is gone
            return 200, answer
        if grant == "urn:ietf:params:oauth:grant-type:device_code":
            device = self.devices.get(form.get("device_code", ""))
            if device is None:
                return 400, {"error": "invalid_grant"}
            if not device["approved"]:
                return 400, {"error": "authorization_pending"}
            del self.devices[form["device_code"]]
            return 200, self._tokens()
        return 400, {"error": "unsupported_grant_type"}

    # HTTP ---------------------------------------------------------------------------------------------------

    def _metadata(self) -> dict[str, Any]:
        i = self.issuer
        return {
            "issuer": i,
            "authorization_endpoint": f"{i}/authorize",
            "token_endpoint": f"{i}/token",
            "userinfo_endpoint": f"{i}/userinfo",
            "revocation_endpoint": f"{i}/revoke",
            "device_authorization_endpoint": f"{i}/device/code",
            "jwks_uri": f"{i}/jwks",
        }

    def _jwks(self) -> dict[str, Any]:
        key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        return {"keys": [{**key, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def _authorize(self, query: dict[str, str]) -> str:
        """Where the browser goes next: straight back to the app, as the real service does once signed in."""
        self.authorize_queries.append(query)
        redirect = query["redirect_uri"]
        url = urlparse(redirect)
        assert query["client_id"] == CLIENT_ID
        assert url.scheme == "http" and url.hostname == "127.0.0.1" and url.path == "/callback", redirect
        assert query["code_challenge_method"] == "S256" and "offline_access" in query["scope"].split()
        if self.deny:
            return f"{redirect}?{urlencode({'error': 'access_denied', 'state': query['state']})}"
        code = secrets.token_urlsafe(16)
        self.codes[code] = {
            "redirect_uri": redirect,
            "code_challenge": query["code_challenge"],
            "nonce": query["nonce"],
        }
        return f"{redirect}?{urlencode({'code': code, 'state': query['state']})}"

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, status: int, body: Any = None, location: str | None = None) -> None:
                data = json.dumps(body).encode() if body is not None else b""
                self.send_response(status)
                if location:
                    self.send_header("Location", location)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802
                if fake.down:
                    return self._send(503, {})
                url = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                if url.path == "/.well-known/openid-configuration":
                    return self._send(200, fake._metadata())
                if url.path == "/jwks":
                    return self._send(200, fake._jwks())
                if url.path == "/authorize":
                    return self._send(302, location=fake._authorize(query))
                if url.path == "/userinfo":
                    token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                    if token not in fake.access_tokens:
                        return self._send(401, {"error": "invalid_token"})
                    info = {**fake.user, "email_verified": True}
                    return self._send(200, info)
                return self._send(404, {})

            def do_POST(self):  # noqa: N802
                if fake.down:
                    return self._send(503, {})
                length = int(self.headers.get("Content-Length") or 0)
                form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
                if self.path == "/token":
                    return self._send(*fake._token(form))
                if self.path == "/revoke":
                    fake.revoked.append(form.get("token", ""))
                    fake.refresh_tokens.pop(form.get("token", ""), None)
                    return self._send(200, {})
                if self.path == "/device/code":
                    device_code, user_code = secrets.token_urlsafe(16), "WDJB-MJHT"
                    fake.devices[device_code] = {"user_code": user_code, "approved": False}
                    return self._send(
                        200,
                        {
                            "device_code": device_code,
                            "user_code": user_code,
                            "verification_uri": f"{fake.issuer}/device",
                            "verification_uri_complete": f"{fake.issuer}/device?user_code={user_code}",
                            "expires_in": 30,
                            "interval": 1,
                        },
                    )
                return self._send(404, {})

            def log_message(self, format, *args):
                pass

        return Handler
