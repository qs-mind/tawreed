import json
import os
import re
import subprocess

import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from tawreed.ai import check, providers


class Refused(Exception):
    status_code = 401


class NotFound(Exception):
    status_code = 404


@pytest.fixture
def models(monkeypatch):
    """The provider's model list; set `.error` to make listing fail. No test ever reaches a real provider."""

    class Listing:
        names = ["model-b", "model-a"]
        error: Exception | None = None

    async def list_models(provider, key, base_url):
        if Listing.error:
            raise Listing.error
        return Listing.names

    monkeypatch.setattr(providers, "list_models", list_models)
    return Listing


def use_model(monkeypatch, respond):
    monkeypatch.setattr(providers, "build_model", lambda *args: FunctionModel(respond))


def follows_instructions(messages, info):
    if len(messages) == 1:
        prompt = next(p.content for p in messages[0].parts if isinstance(p, UserPromptPart))
        code = re.search(r"code is (\w+)", prompt).group(1)
        return ModelResponse(parts=[ToolCallPart("confirm", {"code": code})])
    return ModelResponse(parts=[TextPart("Done.")])


def ignores_tools(messages, info):
    return ModelResponse(parts=[TextPart("Hello!")])


def sees(messages, info):
    """Follows instructions, and reads the check's number from the image (the test fixes it at 123)."""
    if any(isinstance(c, BinaryContent) for m in messages for p in m.parts for c in getattr(p, "content", []) or []):
        return ModelResponse(parts=[TextPart("123")])
    return follows_instructions(messages, info)


def add(client, **body):
    body = {"provider": "anthropic", "api_key": "sk-test-1234abcd", **body}
    return client.post("/ai/connections", json=body)


def checked(client, monkeypatch, respond=follows_instructions, model="model-a"):
    connection = add(client).json()
    use_model(monkeypatch, respond)
    return client.post(f"/ai/connections/{connection['id']}/checks", json={"model": model}).json()


def test_a_working_key_is_kept_in_the_keychain_and_never_returned(client, models, tmp_path, memory_keychain):
    response = add(client)
    assert response.status_code == 201
    connection = response.json()
    assert connection["label"] == "Anthropic"
    assert connection["key_hint"] == "abcd"
    assert "sk-test" not in json.dumps(connection)

    saved = (tmp_path / "connections.json").read_text(encoding="utf-8")
    assert "sk-test" not in saved and json.loads(saved)["connections"][0]["key_hint"] == "abcd"
    assert list(memory_keychain.entries.values()) == ["sk-test-1234abcd"]
    assert not (tmp_path / "auth.json").exists()
    assert client.get("/ai/connections").json() == [connection]
    assert client.get(f"/ai/connections/{connection['id']}/models").json() == ["model-b", "model-a"]


def test_a_refused_key_is_not_kept(client, models, tmp_path):
    models.error = Refused("invalid x-api-key")
    response = add(client)
    assert response.status_code == 400
    assert response.json()["detail"] == {"code": "key_refused"}
    assert not (tmp_path / "connections.json").exists()


@pytest.mark.skipif(os.name == "nt", reason="file modes are POSIX; Windows keeps the files in the user's own profile")
def test_the_connections_file_is_readable_by_the_current_user_only(client, models, tmp_path):
    add(client)
    file = tmp_path / "connections.json"
    if os.name == "nt":
        acl = subprocess.run(["icacls", str(file)], capture_output=True, text=True, check=True).stdout
        entries = [line for line in acl.splitlines()[:-2] if ":" in line.replace(str(file), "")]
        assert len(entries) == 1, acl  # only the current user, nothing inherited
        assert os.environ["USERNAME"].lower() in acl.lower()
    else:
        assert file.stat().st_mode & 0o777 == 0o600


def test_an_openai_compatible_service_needs_an_address(client, models):
    assert add(client, provider="openai_compatible").status_code == 422
    models.error = NotFound("no /models here")
    connection = add(client, provider="openai_compatible", base_url="https://api.example.com/v1").json()
    assert connection["label"] == "api.example.com"
    assert client.get(f"/ai/connections/{connection['id']}/models").json() == []


def test_model_check_needs_real_tool_use(client, models, monkeypatch):
    refused = checked(client, monkeypatch, ignores_tools)["checks"]["model-a"]
    assert (refused["ok"], refused["problem"]) == (False, "no_tool_use")

    connection_id = client.get("/ai/connections").json()[0]["id"]
    requests = []
    use_model(monkeypatch, lambda messages, info: requests.append(1) or follows_instructions(messages, info))
    passed = client.post(f"/ai/connections/{connection_id}/checks", json={"model": "model-a"}).json()
    assert passed["checks"]["model-a"]["ok"] is True
    assert passed["checks"]["model-a"]["problem"] is None
    assert len(requests) == 2  # the tool call is the proof, then one request with an image; no closing replies


def test_the_check_finds_out_whether_a_model_reads_images(client, models, monkeypatch):
    monkeypatch.setattr(check.secrets, "randbelow", lambda n: 23)
    assert checked(client, monkeypatch, follows_instructions)["checks"]["model-a"]["sees_images"] is False
    seeing = checked(client, monkeypatch, sees)["checks"]["model-a"]
    assert seeing | {"checked_at": ""} == {"ok": True, "problem": None, "sees_images": True, "checked_at": ""}


def test_tawreed_only_works_with_a_checked_model(client, models, monkeypatch, tmp_path):
    assert client.get("/settings").json()["ai"] is None
    connection = add(client).json()
    choice = {"connection_id": connection["id"], "model": "model-a"}

    refused = client.patch("/settings", json={"ai": choice})
    assert refused.status_code == 400
    assert refused.json()["detail"] == {"code": "model_not_checked"}
    unknown = client.patch("/settings", json={"ai": {"connection_id": "nope", "model": "model-a"}})
    assert unknown.json()["detail"] == {"code": "connection_not_found"}

    use_model(monkeypatch, follows_instructions)
    client.post(f"/ai/connections/{connection['id']}/checks", json={"model": "model-a"})
    assert client.patch("/settings", json={"ai": choice}).json()["ai"] == choice
    assert client.patch("/settings", json={"theme": "dark"}).json() == {"language": "en", "theme": "dark", "ai": choice}
    assert client.patch("/settings", json={"ai": None}).json()["ai"] is None
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["ai"] is None


def test_removing_a_connection_clears_the_choice(client, models, monkeypatch):
    connection = checked(client, monkeypatch)
    client.patch("/settings", json={"ai": {"connection_id": connection["id"], "model": "model-a"}})

    assert client.delete(f"/ai/connections/{connection['id']}").status_code == 204
    assert client.get("/ai/connections").json() == []
    assert client.get("/settings").json()["ai"] is None
    assert client.delete(f"/ai/connections/{connection['id']}").status_code == 404


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (Refused(), ("key_refused", {})),
        (NotFound(), ("model_missing", {})),
        (type("Limited", (Exception,), {"status_code": 429})(), ("rate_limited", {})),
        (type("APIConnectionError", (Exception,), {})(), ("unreachable", {})),
        (type("APITimeoutError", (Exception,), {})(), ("timed_out", {})),
        (type("Odd", (Exception,), {"status_code": 500})(), ("service_error", {"status": "500"})),
    ],
)
def test_failures_become_codes_the_interface_can_explain(error, code):
    assert providers.explain(error) == code


def test_a_wrapped_provider_error_is_explained_from_its_cause():
    try:
        try:
            raise type("APITimeoutError", (Exception,), {})()
        except Exception as timeout:
            raise ModelAPIError("some-model", "Request timed out.") from timeout
    except ModelAPIError as wrapped:
        assert providers.explain(wrapped) == ("timed_out", {})
