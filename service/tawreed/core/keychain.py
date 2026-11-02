"""Secrets in the operating system's keychain: Windows Credential Manager, the macOS Keychain or the Linux Secret
Service, through `keyring`. Tawreed keeps the QS Mind refresh token and the AI keys here, never in ~/.tawreed.

Entries sit under the service name `com.qsmind.tawreed`. A data home other than ~/.tawreed (TAWREED_HOME, for tests
and scratch runs) gets a service name of its own, so it never reads or replaces the real entries."""

from pathlib import Path

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE = "com.qsmind.tawreed"


class Unavailable(Exception):
    """The keychain can't be reached or refused the entry (none installed, locked, a write that didn't stick)."""


def _service(home: Path) -> str:
    here = home.resolve()
    return SERVICE if here == (Path.home() / ".tawreed").resolve() else f"{SERVICE}:{here}"


def read(home: Path, name: str) -> str | None:
    try:
        return keyring.get_password(_service(home), name)
    except (KeyringError, RuntimeError) as error:
        raise Unavailable(str(error)) from error


def write(home: Path, name: str, value: str) -> None:
    """Keep the secret, then read it back: it counts as kept only when the keychain returns it unchanged."""
    try:
        keyring.set_password(_service(home), name, value)
    except (KeyringError, RuntimeError) as error:
        raise Unavailable(str(error)) from error
    if read(home, name) != value:
        raise Unavailable(f"{name} did not read back as written")


def delete(home: Path, name: str) -> None:
    """Forget the secret; one that isn't there is already forgotten."""
    try:
        keyring.delete_password(_service(home), name)
    except PasswordDeleteError:
        pass
    except (KeyringError, RuntimeError) as error:
        raise Unavailable(str(error)) from error
