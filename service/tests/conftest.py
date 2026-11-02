import keyring
import pytest
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from tawreed.account.session import Account
from tawreed.api.app import create_app

TOKEN = "test-token"


def pytest_configure(config):
    config.addinivalue_line("markers", "account: runs with the real account state instead of a signed-in one")


class MemoryKeychain(KeyringBackend):
    """The operating system's keychain, in memory: no test reads or writes the real one."""

    priority = 1

    def __init__(self):
        super().__init__()
        self.entries: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.entries.get((service, username))

    def set_password(self, service, username, password):
        self.entries[(service, username)] = password

    def delete_password(self, service, username):
        if self.entries.pop((service, username), None) is None:
            raise PasswordDeleteError(username)


@pytest.fixture(autouse=True)
def memory_keychain():
    before = keyring.get_keyring()
    chain = MemoryKeychain()
    keyring.set_keyring(chain)
    yield chain
    keyring.set_keyring(before)


@pytest.fixture(autouse=True)
def signed_in(request, monkeypatch):
    """Tests of the rest of Tawreed run signed in to QS Mind; tests marked `account` sign in for themselves."""
    if "account" not in request.keywords:
        monkeypatch.setattr(Account, "writable", lambda self: True)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"}) as c:
        yield c
