"""Per-account password policy and alias behavior."""

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


def configured(tmp_path, *, policy="yes", alias=None, auto_login=True):
    config = Config(tmp_path / "config.json")
    config.update(
        accounts=[
            _account(
                "complicated.address@example.com",
                alias=alias,
                save_password=policy,
                auto_login=auto_login,
            ),
        ],
    )
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


def test_yes_policy_reads_keyring_without_prompt(tmp_path, monkeypatch, keyring_stub):
    config, accounts = configured(tmp_path, alias="MyToon")
    keyring_stub["complicated.address@example.com"] = "secret"
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr(
        "gttrl.cli._prompt_text",
        lambda *args, **kwargs: pytest.fail("Saved secret should not prompt"),
    )
    auth = FakeAuth()
    assert _authenticate(auth, accounts, config, accounts.usernames[0], None, True)
    assert auth.attempts == [("complicated.address@example.com", "secret")]


def test_never_policy_neither_reads_nor_saves_keyring(tmp_path, monkeypatch):
    config, accounts = configured(tmp_path, policy="never")
    monkeypatch.setattr(
        accounts, "keyring_password",
        lambda username: pytest.fail("Never must not read the keyring"),
    )
    monkeypatch.setattr("gttrl.cli._prompt_text", lambda *args, **kwargs: "manual")
    monkeypatch.setattr(
        "gttrl.cli._select",
        lambda *args: pytest.fail("Never should not prompt about policy on normal login"),
    )
    auth = FakeAuth()
    assert _authenticate(auth, accounts, config, accounts.usernames[0], None, True)
    assert auth.attempts[0][1] == "manual"
    assert accounts.account(accounts.usernames[0])["save_password"] == "never"


def test_ask_policy_explicitly_asks_what_to_do(tmp_path, monkeypatch):
    config, accounts = configured(tmp_path, policy="ask")
    prompts = []
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr("gttrl.cli._prompt_text", lambda *args, **kwargs: "manual")

    def choose(message, options):
        prompts.append((message, [value for _, value in options]))
        return "manual" if message.startswith("How should") else "ask"

    monkeypatch.setattr("gttrl.cli._select", choose)
    auth = FakeAuth()
    assert _authenticate(auth, accounts, config, accounts.usernames[0], None, True)
    assert auth.attempts[0][1] == "manual"
    assert prompts[0][1] == ["keyring", "manual", "skip"]
    assert prompts[1][1] == ["yes", "ask", "never"]
    assert accounts.account(accounts.usernames[0])["save_password"] == "ask"


def test_failed_yes_keyring_falls_back_to_password_then_new_policy(
    tmp_path, monkeypatch, keyring_stub
):
    config, accounts = configured(tmp_path, policy="yes")
    keyring_stub.clear()
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr("gttrl.cli._prompt_text", lambda *args, **kwargs: "new-secret")
    monkeypatch.setattr("gttrl.cli._select", lambda *args: "never")
    auth = FakeAuth()
    assert _authenticate(auth, accounts, config, accounts.usernames[0], None, True)
    assert auth.attempts[0][1] == "new-secret"
    assert accounts.account(accounts.usernames[0])["save_password"] == "never"
    assert not keyring_stub


def test_rejected_yes_keyring_prompts_retry_and_updates_saved_secret(
    tmp_path, monkeypatch, keyring_stub
):
    config, accounts = configured(tmp_path, policy="yes")
    user = accounts.usernames[0]
    keyring_stub[user] = "old-secret"
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr("gttrl.cli._prompt_text", lambda *args, **kwargs: "replacement")
    options = iter(["retry", "yes"])
    monkeypatch.setattr("gttrl.cli._select", lambda *args: next(options))
    auth = FakeAuth(rejected_password="old-secret")
    assert _authenticate(auth, accounts, config, user, None, True)
    assert auth.attempts == [(user, "old-secret"), (user, "replacement")]
    assert keyring_stub[user] == "replacement"


def test_aliases_resolve_and_remain_clear_of_secrets(tmp_path, keyring_stub):
    config, accounts = configured(tmp_path, alias="RedToon")
    user = accounts.usernames[0]
    assert accounts.resolve("RedToon") == user
    assert accounts.label(user) == f"RedToon ({user})"
    accounts.set_alias("RedToon", "PurpleToon")
    assert accounts.resolve("PurpleToon") == user
    accounts.set_auto_login(["PurpleToon"])
    assert accounts.auto_login_accounts == [user]
    assert "PurpleToon" in config.path.read_text()
    assert '"password":' not in config.path.read_text()


def test_alias_command_and_password_policy_command(
    tmp_path, monkeypatch, keyring_stub
):
    config, accounts = configured(tmp_path, policy="yes")
    user = accounts.usernames[0]
    keyring_stub[user] = "secret"
    runner = CliRunner()
    alias = runner.invoke(
        main, ["accounts", "--config-path", str(config.path), "alias", user, "RedToon"]
    )
    assert alias.exit_code == 0, alias.output
    assert Accounts(Config(config.path)).resolve("RedToon") == user
    policy = runner.invoke(
        main, [
            "accounts", "--config-path", str(config.path),
            "save-password", "RedToon", "never",
        ]
    )
    assert policy.exit_code == 0, policy.output
    assert user not in keyring_stub
    assert Accounts(Config(config.path)).account(user)["save_password"] == "never"
    cleared = runner.invoke(
        main, ["accounts", "--config-path", str(config.path), "alias", user, "--clear"]
    )
    assert cleared.exit_code == 0, cleared.output
    assert Accounts(Config(config.path)).account(user)["alias"] is None


def test_add_without_keyring_if_never(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "gttrl.credentials.keyring.get_keyring",
        lambda: pytest.fail("Never-save must not ask for keyring"),
    )
    config = Config(tmp_path / "config.json")
    accounts = Accounts(config)
    accounts.add("bob", "unsaved", save_password="never", auto_login=True)
    assert accounts.account("bob")["save_password"] == "never"
    assert accounts.auto_login_accounts == ["bob"]
    assert "unsaved" not in config.path.read_text()
    accounts.remove("bob")
    assert accounts.usernames == []


def test_duplicate_aliases_cannot_be_registered(tmp_path, keyring_stub):
    _config, accounts = configured(tmp_path, alias="Friendly")
    with pytest.raises(CredentialError):
        accounts.resolve("Unknown")
    with pytest.raises(Exception, match="Aliases must not conflict"):
        accounts.add("Friendly", "pass", alias="Another")
    assert accounts.usernames == ["complicated.address@example.com"]
