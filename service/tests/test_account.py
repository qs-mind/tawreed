"""Sign in with QS Mind, against a fake account service on loopback (tests/fake_oidc.py) and an in-memory keychain.
No test reaches auth.qsmind.app or the real keychain."""

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fake_oidc import CLIENT_ID, FakeOIDC
from fastapi.testclient import TestClient
from keyring.errors import KeyringError

from tawreed.account import session
from tawreed.ai import connections
from tawreed.api.app import create_app
from tawreed.core import env, keychain

pytestmark = pytest.mark.account
TOKEN = "test-token"


@pytest.fixture
def oidc(monkeypatch):
    fake = FakeOIDC()
    monkeypatch.setenv("TAWREED_AUTH_ISSUER", fake.issuer)
    monkeypatch.setenv("TAWREED_AUTH_CLIENT_ID", CLIENT_ID)
    yield fake
    fake.close()


@pytest.fixture
def opened(monkeypatch):
    """The addresses Tawreed opened in the system browser."""
    urls: list[str] = []
    monkeypatch.setattr(env, "open_url", urls.append)
    return urls


class Clock:
    def __init__(self):
        self.at = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)

    def __call__(self):
        return self.at

    def pass_(self, **delta):
        self.at += timedelta(**delta)


@pytest.fixture
def app(tmp_path, oidc, opened):
    with TestClient(create_app(tmp_path, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"}) as c:
        c.clock = Clock()
        c.app.state.account.now = c.clock
        yield c


def browser(url: str) -> httpx.Response:
    """The person in the browser: already signed in at QS Mind, the account sends them straight back to Tawreed."""
    to_tawreed = httpx.get(url, follow_redirects=False)
    assert to_tawreed.status_code == 302
    return httpx.get(to_tawreed.headers["location"])


def settled(app, condition, seconds=5.0) -> dict:
    """The account once the background refresh has done what the test waits for."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        account = app.get("/account").json()
        if condition(account):
            return account
        time.sleep(0.02)
    raise AssertionError(f"the account did not get there: {app.get('/account').json()}")


def sign_in(app, opened) -> dict:
    assert app.post("/account/sign-in", json={"language": "en"}).status_code == 200
    page = browser(opened[-1])
    assert page.status_code == 200, page.text
    return app.get("/account").json()


def test_tawreed_is_signed_out_until_the_engineer_signs_in_and_changes_wait(app):
    account = app.get("/account").json()
    assert account["state"] == "signed_out"
    assert app.get("/projects").status_code == 200
    refused = app.post("/projects", files=[("files", ("a.csv", b"Code,Qty\n1,2\n"))])
    assert (refused.status_code, refused.json()["detail"]["code"]) == (403, "sign_in_required")


def test_signing_in_through_the_browser(app, oidc, opened, tmp_path, memory_keychain):
    started = app.post("/account/sign-in", json={"language": "ar"}).json()
    assert started["pending"]["method"] == "browser"
    assert opened == [started["pending"]["url"]]
    query = httpx.URL(opened[0]).params
    assert query["redirect_uri"].startswith("http://127.0.0.1:") and query["redirect_uri"].endswith("/callback")
    assert query["scope"] == "openid profile email offline_access" and query["ui_locales"] == "ar"
    assert query["code_challenge_method"] == "S256" and query["state"] and query["nonce"]

    page = browser(opened[0])
    assert page.status_code == 200 and "توريد" in page.text

    account = app.get("/account").json()
    assert account["state"] == "active"
    assert (account["email"], account["name"], account["plan"]) == ("eng@example.test", "Mona Adel", None)
    assert account["pending"] is None and account["problem"] is None
    assert account["lease_ends_at"] == (app.clock() + timedelta(days=session.LEASE_DAYS)).isoformat()

    # The refresh token is in the keychain and nowhere in the data folder.
    [token] = [v for (_, name), v in memory_keychain.entries.items() if name == session.REFRESH_TOKEN]
    assert token in oidc.refresh_tokens
    assert all(token not in f.read_text(errors="ignore") for f in tmp_path.rglob("*") if f.is_file())
    assert json.loads((tmp_path / "account.json").read_text())["sub"] == oidc.user["sub"]

    # Signed in, changes go through.
    assert app.post("/projects", files=[("files", ("a.csv", b"Code,Qty\n1,2\n"))]).status_code == 201


def test_the_plan_comes_from_the_account_when_it_sends_one(app, oidc, opened):
    oidc.plan = "pro"
    assert sign_in(app, opened)["plan"] == "pro"


def test_a_refused_sign_in_says_so_and_stays_signed_out(app, oidc, opened):
    oidc.deny = True
    account = sign_in(app, opened)
    assert (account["state"], account["problem"]) == ("signed_out", "sign_in_denied")


def test_a_redirect_from_another_sign_in_is_ignored(app, opened):
    app.post("/account/sign-in", json={"language": "en"})
    redirect = httpx.URL(opened[0]).params["redirect_uri"]
    assert httpx.get(redirect, params={"code": "x", "state": "not-this-one"}).status_code == 400
    assert httpx.get(redirect.replace("/callback", "/favicon.ico")).status_code == 404
    assert app.get("/account").json()["pending"]["method"] == "browser"  # still waiting for the real one


def test_cancelling_a_sign_in(app, opened):
    app.post("/account/sign-in", json={"language": "en"})
    assert app.delete("/account/sign-in").status_code == 204
    assert app.get("/account").json()["pending"] is None


def test_signing_in_with_a_code(app, oidc, opened):
    started = app.post("/account/sign-in/code", json={"language": "en"}).json()
    assert started["pending"]["method"] == "code" and started["pending"]["user_code"] == "WDJB-MJHT"
    assert opened == [f"{oidc.issuer}/device?user_code=WDJB-MJHT"]
    oidc.approve_device("WDJB-MJHT")
    for _ in range(50):
        if app.get("/account").json()["state"] == "active":
            break
        time.sleep(0.1)
    assert app.get("/account").json()["email"] == "eng@example.test"


def test_the_account_is_refreshed_hourly_and_the_new_token_kept(app, oidc, opened, memory_keychain):
    sign_in(app, opened)
    first = memory_keychain.entries[next(k for k in memory_keychain.entries if k[1] == session.REFRESH_TOKEN)]
    app.clock.pass_(minutes=30)
    app.get("/account")
    assert first in oidc.refresh_tokens  # not due yet
    app.clock.pass_(minutes=31)
    renewed = (app.clock() + timedelta(days=14)).isoformat()
    assert settled(app, lambda a: a["lease_ends_at"] == renewed)["state"] == "active"
    second = memory_keychain.entries[next(k for k in memory_keychain.entries if k[1] == session.REFRESH_TOKEN)]
    assert second != first and second in oidc.refresh_tokens and first not in oidc.refresh_tokens


def test_offline_tawreed_works_for_the_lease_then_is_read_only_and_loses_nothing(app, oidc, opened):
    sign_in(app, opened)
    project = app.post("/projects", files=[("files", ("a.csv", b"Code,Qty\n1,2\n"))]).json()
    oidc.down = True

    app.clock.pass_(days=13, hours=23)
    settled(app, lambda a: a["state"] == "offline")
    assert app.patch(f"/projects/{project['id']}", json={"name": "Still works"}).status_code == 200

    app.clock.pass_(hours=1)
    assert app.get("/account").json()["state"] == "expired"
    refused = app.patch(f"/projects/{project['id']}", json={"name": "Not now"})
    assert (refused.status_code, refused.json()["detail"]["code"]) == (403, "read_only")
    assert app.get(f"/projects/{project['id']}").json()["name"] == "Still works"  # everything still reads

    oidc.down = False
    app.clock.pass_(minutes=5)  # the next try, once the account service answers again
    settled(app, lambda a: a["state"] == "active")
    assert app.patch(f"/projects/{project['id']}", json={"name": "Back"}).status_code == 200


def test_a_refused_refresh_signs_out_and_keeps_the_projects(app, oidc, opened, memory_keychain):
    sign_in(app, opened)
    app.post("/projects", files=[("files", ("a.csv", b"Code,Qty\n1,2\n"))])
    oidc.revoke_everything()  # signed out everywhere, on the account page
    app.clock.pass_(hours=2)
    settled(app, lambda a: a["state"] == "signed_out")
    assert not any(name == session.REFRESH_TOKEN for _, name in memory_keychain.entries)
    assert len(app.get("/projects").json()) == 1


def test_signing_out_revokes_the_token_and_forgets_it(app, oidc, opened, memory_keychain, tmp_path):
    sign_in(app, opened)
    app.post("/projects", files=[("files", ("a.csv", b"Code,Qty\n1,2\n"))])
    token = memory_keychain.entries[next(k for k in memory_keychain.entries if k[1] == session.REFRESH_TOKEN)]
    assert app.post("/account/sign-out").status_code == 204
    assert oidc.revoked == [token]
    assert app.get("/account").json()["state"] == "signed_out"
    assert not (tmp_path / "account.json").exists()
    assert not any(name == session.REFRESH_TOKEN for _, name in memory_keychain.entries)
    assert len(app.get("/projects").json()) == 1


def test_signing_out_offline_still_signs_out_here(app, oidc, opened):
    sign_in(app, opened)
    oidc.down = True
    assert app.post("/account/sign-out").status_code == 204
    assert app.get("/account").json()["state"] == "signed_out"


def test_sign_in_without_a_registered_client_says_so(app, monkeypatch):
    monkeypatch.delenv("TAWREED_AUTH_CLIENT_ID")
    monkeypatch.setattr(session, "CLIENT_ID", "")
    app.app.state.account._client = None
    refused = app.post("/account/sign-in", json={"language": "en"})
    assert (refused.status_code, refused.json()["detail"]["code"]) == (503, "sign_in_unavailable")


def test_sign_in_with_the_account_service_down_says_so(app, oidc):
    oidc.down = True
    refused = app.post("/account/sign-in", json={"language": "en"})
    assert (refused.status_code, refused.json()["detail"]["code"]) == (503, "auth_failed")


def test_without_a_keychain_sign_in_says_so(app, opened, memory_keychain, monkeypatch):
    def broken(*args):
        raise KeyringError("no Secret Service")

    monkeypatch.setattr(memory_keychain, "set_password", broken)
    account = sign_in(app, opened)
    assert (account["state"], account["problem"]) == ("signed_out", "keychain_unavailable")


# The AI keys move to the keychain ----------------------------------------------------------------------------


def old_auth_json(home):
    data: dict = {
        "connections": [
            {"id": "c1", "provider": "openai", "label": "OpenAI", "base_url": None, "api_key": "sk-old-9876"},
            {"id": "c2", "provider": "codex", "label": "Codex", "base_url": None, "api_key": ""},
        ]
    }
    for connection in data["connections"]:
        connection["checks"] = {}
    (home / "auth.json").write_text(json.dumps(data), encoding="utf-8")


def test_keys_in_an_old_auth_json_move_to_the_keychain_once(tmp_path, memory_keychain):
    old_auth_json(tmp_path)
    connections.migrate(tmp_path)
    assert not (tmp_path / "auth.json").exists()
    saved = (tmp_path / "connections.json").read_text(encoding="utf-8")
    assert "sk-old" not in saved
    assert [c["key_hint"] for c in json.loads(saved)["connections"]] == ["9876", ""]
    assert connections.get(tmp_path, "c1")["api_key"] == "sk-old-9876"
    assert connections.get(tmp_path, "c2")["api_key"] == ""
    assert list(memory_keychain.entries.values()) == ["sk-old-9876"]


def test_the_old_file_stays_when_the_keychain_fails(tmp_path, memory_keychain, monkeypatch):
    old_auth_json(tmp_path)
    monkeypatch.setattr(memory_keychain, "get_password", lambda service, name: "something else")
    connections.migrate(tmp_path)
    assert (tmp_path / "auth.json").exists()  # nothing lost: tried again at the next start


def test_the_service_moves_the_keys_when_it_starts(tmp_path):
    old_auth_json(tmp_path)
    with TestClient(create_app(tmp_path, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"}) as c:
        assert [x["key_hint"] for x in c.get("/ai/connections").json()] == ["9876", ""]
    assert not (tmp_path / "auth.json").exists()


def test_a_scratch_data_folder_keeps_its_own_keychain_entries(tmp_path):
    keychain.write(tmp_path, "x", "1")
    assert keychain._service(tmp_path) != keychain.SERVICE
    assert keychain._service(Path.home() / ".tawreed") == keychain.SERVICE
