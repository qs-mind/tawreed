"""AI connections: the details in ~/.tawreed/connections.json, each key in the operating system's keychain.

The file holds no key, only its last four characters to show. Keys never leave the service except to their own
provider. Earlier versions kept keys in a plain ~/.tawreed/auth.json; `migrate` moves them once."""

import logging
import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tawreed.core import jsonfile, keychain

log = logging.getLogger("tawreed.ai")


def path(home: Path) -> Path:
    return home / "connections.json"


def _old_path(home: Path) -> Path:
    return home / "auth.json"


def _key_name(connection_id: str) -> str:
    return f"ai-key:{connection_id}"


def _empty() -> dict[str, Any]:
    return {"connections": []}


def all_connections(home: Path) -> list[dict[str, Any]]:
    """Every connection's details, without its key."""
    return jsonfile.read(path(home), _empty())["connections"]


def get(home: Path, connection_id: str) -> dict[str, Any] | None:
    """The connection with its key from the keychain ("" for Codex, which keeps its own sign-in).
    Raises keychain.Unavailable when the keychain can't give the key."""
    connection = next((c for c in all_connections(home) if c["id"] == connection_id), None)
    if connection is None:
        return None
    key = keychain.read(home, _key_name(connection_id)) if connection["key_hint"] else ""
    return {**connection, "api_key": key or ""}


def add(home: Path, provider: str, label: str, api_key: str, base_url: str | None) -> dict[str, Any]:
    connection = {
        "id": uuid.uuid4().hex,
        "provider": provider,
        "label": label,
        "base_url": base_url,
        "key_hint": api_key[-4:],
        "checks": {},
    }
    if api_key:
        keychain.write(home, _key_name(connection["id"]), api_key)
    _update(home, lambda data: data["connections"].append(connection))
    return connection


def remove(home: Path, connection_id: str) -> None:
    def change(data: dict[str, Any]) -> None:
        data["connections"] = [c for c in data["connections"] if c["id"] != connection_id]

    _update(home, change)
    keychain.delete(home, _key_name(connection_id))


def record_check(home: Path, connection_id: str, model: str, ok: bool, problem: str | None, sees_images: bool) -> None:
    result = {"ok": ok, "problem": problem, "sees_images": sees_images, "checked_at": datetime.now(UTC).isoformat()}

    def change(data: dict[str, Any]) -> None:
        for connection in data["connections"]:
            if connection["id"] == connection_id:
                connection["checks"][model] = result

    _update(home, change)


def migrate(home: Path) -> None:
    """Move an earlier version's auth.json into the keychain and connections.json, once. The plain file is deleted
    only after every key reads back from the keychain and every connection from connections.json; on any failure it
    stays as it is and the move is tried again at the next start."""
    old = _old_path(home)
    if not old.exists():
        return
    moved = jsonfile.read(old, _empty())["connections"]
    try:
        for connection in moved:
            if connection.get("api_key"):
                keychain.write(home, _key_name(connection["id"]), connection["api_key"])
        details = [
            {**{k: v for k, v in c.items() if k != "api_key"}, "key_hint": (c.get("api_key") or "")[-4:]} for c in moved
        ]

        def change(data: dict[str, Any]) -> None:
            known = {c["id"] for c in data["connections"]}
            data["connections"].extend(c for c in details if c["id"] not in known)

        _update(home, change)
        kept = {c["id"]: c for c in all_connections(home)}
        for connection in moved:
            key = connection.get("api_key") or ""
            if connection["id"] not in kept or (key and keychain.read(home, _key_name(connection["id"])) != key):
                raise keychain.Unavailable(f"connection {connection['id']} did not read back")
    except (keychain.Unavailable, OSError, KeyError) as error:
        log.error("AI keys stay in auth.json for now; moving them to the keychain failed: %s", error)
        return
    old.unlink()
    log.info("Moved %d AI connection(s) from auth.json to the keychain", len(moved))


def _update(home: Path, change) -> None:
    jsonfile.update(path(home), _empty(), change)
    make_private(path(home))


def make_private(file: Path) -> None:
    """Let only the current user read or change the file."""
    try:
        if os.name == "nt":
            # By security ID rather than name, so domain and Microsoft accounts work too.
            sid = _run(["whoami", "/user", "/fo", "csv", "/nh"]).strip().split(",")[-1].strip('"')
            _run(["icacls", str(file), "/inheritance:r", "/grant:r", f"*{sid}:F"])
        else:
            file.chmod(0o600)
    except (OSError, subprocess.CalledProcessError) as error:
        log.warning("Could not restrict %s to the current user: %s", file.name, error)


def _run(command: list[str]) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout
