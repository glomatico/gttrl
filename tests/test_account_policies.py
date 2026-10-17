"""Per-account boolean password saving and secure recovery behavior."""

import pytest
from click.testing import CliRunner

from gttrl.auth import LoginRejected
from gttrl.cli import _authenticate, main
from gttrl.config import Config, _account
from gttrl.credentials import Accounts, CredentialError
from gttrl.models import LoginResponse


@pytest.fixture
def keyring_stub(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        "gttrl.credentials.keyring.get_keyring",
        lambda: type("Backend", (), {"priority": 1})(),
    )
    monkeypatch.setattr(
        "gttrl.credentials.keyring.set_password",
        lambda service, user, password: saved.__setitem__(user, password),
    )
    monkeypatch.setattr(
        "gttrl.credentials.keyring.get_password",
        lambda service, user: saved.get(user),
    )
    monkeypatch.setattr(
        "gttrl.credentials.keyring.delete_password",
        lambda service, user: saved.pop(user, None),
    )
    return saved


def configured(tmp_path, *, save=True, alias=None, auto_launch=True):
    config = Config(tmp_path / "config.json")
    config.set("accounts", [
        _account(
            "complicated.address@example.com",
            alias=alias,
            save_password=save,
            auto_launch=auto_launch,
        )
    ])
    return config, Accounts(config)


class FakeAuth:
    def __init__(self, rejected_password=None):
        self.rejected_password = rejected_password
        self.attempts = []

    def login(self, username, password, **kwargs):
        self.attempts.append((username, password))
        if password == self.rejected_password:
            raise LoginRejected("Incorrect password")
        return LoginResponse("cookie", "host")


def test_saved_password_reads_keyring_without_prompt(tmp_path, monkeypatch, keyring_stub):
    config, accounts = configured(tmp_path, alias="MyToon")
    user = accounts.usernames[0]
    keyring_stub[user] = "secret"
    monkeypatch.setattr(
        "gttrl.cli._prompt_text",
        lambda *args, **kwargs: pytest.fail("Saved password shouldn't prompt"),
    )
    auth = FakeAuth()
    assert _authenticate(auth, accounts, config, user, None, True)
    assert auth.attempts == [(user, "secret")]


def test_unsaved_password_always_prompts_and_never_uses_keyring(tmp_path, monkeypatch):
    config, accounts = configured(tmp_path, save=False)
    monkeypatch.setattr(
        accounts, "keyring_password",
        lambda username: pytest.fail("Keyring must not be read when disabled"),
    )
    monkeypatch.setattr("gttrl.cli._prompt_text", lambda *args, **kwargs: "manual")
    auth = FakeAuth()
    assert _authenticate(auth, accounts, config, accounts.usernames[0], None, True)
    assert auth.attempts[0][1] == "manual"
    assert accounts.account(accounts.usernames[0])["save_password"] is False


def test_missing_keyring_password_prompt_and_save_after_success(
    tmp_path, monkeypatch, keyring_stub
):
    config, accounts = configured(tmp_path)
    user = accounts.usernames[0]
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    prompts = []

    def prompt(message, **kwargs):
        prompts.append(message)
        return "new-password"

    monkeypatch.setattr("gttrl.cli._prompt_text", prompt)
    auth = FakeAuth()
    assert _authenticate(auth, accounts, config, user, None, True)
    assert auth.attempts == [(user, "new-password")]
    assert keyring_stub[user] == "new-password"
    assert len(prompts) == 1
    auth = FakeAuth()
    monkeypatch.setattr(
        "gttrl.cli._prompt_text",
        lambda *args, **kwargs: pytest.fail("Now saved: do not prompt again"),
    )
    assert _authenticate(auth, accounts, config, user, None, True)
    assert auth.attempts == [(user, "new-password")]


def test_invalid_password_does_not_overwrite_keyring(
    tmp_path, monkeypatch, keyring_stub
):
    config, accounts = configured(tmp_path)
    user = accounts.usernames[0]
    monkeypatch.setattr("gttrl.cli._interactive", lambda: False)
    with pytest.raises(CredentialError):
        _authenticate(FakeAuth(), accounts, config, user, None, True)
    assert not keyring_stub


def test_rejected_keyring_password_replaced_after_success(
    tmp_path, monkeypatch, keyring_stub
):
    config, accounts = configured(tmp_path)
    user = accounts.usernames[0]
    keyring_stub[user] = "old-password"
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr("gttrl.cli._select", lambda *args: "retry")
    monkeypatch.setattr("gttrl.cli._prompt_text", lambda *args, **kwargs: "new-password")
    auth = FakeAuth(rejected_password="old-password")
    assert _authenticate(auth, accounts, config, user, None, True)
    assert auth.attempts == [(user, "old-password"), (user, "new-password")]
    assert keyring_stub[user] == "new-password"


def test_aliases_are_identifiers_and_secret_free(tmp_path, keyring_stub):
    config, accounts = configured(tmp_path, alias="RedToon")
    user = accounts.usernames[0]
    assert accounts.resolve("RedToon") == user
    accounts.set_alias("RedToon", "PurpleToon")
    assert accounts.resolve("PurpleToon") == user
    accounts.set_auto_launch(["PurpleToon"])
    assert accounts.auto_launch_accounts == [user]
    assert "PurpleToon" in config.path.read_text()
    assert '"password":' not in config.path.read_text()


def test_disable_password_saving_removes_keyring_and_requires_password_next_time(
    tmp_path, monkeypatch, keyring_stub
):
    config, accounts = configured(tmp_path)
    user = accounts.usernames[0]
    keyring_stub[user] = "old"
    result = CliRunner().invoke(
        main, ["accounts", "--config-path", str(config.path), "save-password", user, "disable"]
    )
    assert result.exit_code == 0, result.output
    assert user not in keyring_stub
    config = Config(config.path)
    accounts = Accounts(config)
    assert accounts.account(user)["save_password"] is False
    monkeypatch.setattr("gttrl.cli._prompt_text", lambda *args, **kwargs: "manual")
    auth = FakeAuth()
    assert _authenticate(auth, accounts, config, user, None, True)
    assert auth.attempts[0][1] == "manual"


def test_add_without_keyring_when_not_saving_password(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "gttrl.credentials.keyring.get_keyring",
        lambda: pytest.fail("No keyring needed"),
    )
    accounts = Accounts(Config(tmp_path / "config.json"))
    accounts.add("bob", "unsaved", save_password=False, auto_launch=True)
    assert accounts.auto_launch_accounts == ["bob"]
    assert "unsaved" not in accounts.config.path.read_text()
    accounts.remove("bob")
    assert accounts.usernames == []


def test_unique_alias_validation(tmp_path, keyring_stub):
    _config, accounts = configured(tmp_path, alias="Friendly")
    with pytest.raises(CredentialError):
        accounts.resolve("Unknown")
    with pytest.raises(Exception, match="Aliases must not conflict"):
        accounts.add("Friendly", "pass", alias="Another")
    assert accounts.usernames == ["complicated.address@example.com"]
