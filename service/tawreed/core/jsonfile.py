"""Small JSON files under the data home (settings.json, connections.json, account.json)."""

import json
import logging
import os
import shutil
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger("tawreed.core")
_lock = threading.Lock()


def read(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    """The file's content, or `default` when there is none. A file that can't be read as a JSON object is kept
    beside itself as `<name>.bad` (so nothing the engineer typed is lost) and the defaults are used."""
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
        return data
    except (ValueError, OSError) as error:  # JSONDecodeError and UnicodeDecodeError are ValueErrors
        log.error(
            "%s can't be read (%s); a copy is kept as %s.bad and the defaults are used", path.name, error, path.name
        )
        try:
            shutil.copy2(path, path.with_name(path.name + ".bad"))
        except OSError:
            log.exception("Could not keep a copy of %s", path.name)
        return default


def update(path: Path, default: dict[str, Any], change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Read, change and write back in one step, so two requests can't overwrite each other. The temporary file is
    created readable by the current user only, so a key is never on disk with wider access, even briefly."""
    with _lock:
        data = read(path, default)
        change(data)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return data
