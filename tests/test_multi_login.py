"""Multi-toon startup and saved-account recovery regressions."""

import pytest
from click.testing import CliRunner

from gttrl.auth import LoginError, LoginRejected
from gttrl.cli import _ask_save, _authenticate, main
from gttrl.config import Config
from gttrl.credentials import Accounts
from gttrl.models import LoginResponse


def test_auto_login_selection_commands(tmp_path):
    path = tmp_path / "config.json"
    settings = Config(path)
    settings.update(accounts=["alice", "bob", "charlie"], default_account="alice")
    runner = CliRunner()

    def invoke(*args):
        return runner.invoke(main, ["accounts", "--config-path", str(path), "auto-login", *args])

    assert invoke("set", "alice", "bob").exit_code == 0
    assert invoke("list").output == "alice\nbob\n"
    assert Config(path).get("auto_login") is True
    listed = runner.invoke(main, ["accounts", "--config-path", str(path), "list"])
    assert "alice (default) (auto-login)" in listed.output
    assert "bob (auto-login)" in listed.output
    assert "charlie" in listed.output
    assert invoke("off").exit_code == 0
    assert Config(path).get("auto_login_accounts") == []
    assert invoke("on").exit_code == 0
    assert Config(path).get("auto_login_accounts") == ["alice"]
    invalid = invoke("set", "nonexistent")
    assert invalid.exit_code != 0
    assert Config(path).get("auto_login_accounts") == ["alice"]


def test_interactive_multi_select(tmp_path, monkeypatch):
    settings = Config(tmp_path / "config.json")
    settings.update(
        accounts=["alice", "bob"], default_account="alice",
        auto_login=True, auto_login_accounts=["alice"],
    )
    captured = {}
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)

    class FakeCheckbox:
        def ask(self):
            return ["alice", "bob"]

    def checkbox(message, choices):
        captured["choices"] = choices
        return FakeCheckbox()

    monkeypatch.setattr("gttrl.cli.questionary.checkbox", checkbox)
    result = CliRunner().invoke(
        main, ["accounts", "--config-path", str(settings.path), "auto-login"]
    )
    assert result.exit_code == 0, result.output
    assert [choice.checked for choice in captured["choices"]] == [True, False]
    assert Config(settings.path).get("auto_login_accounts") == ["alice", "bob"]


def test_automatic_multi_login_updates_once_and_spawns_distinct_games(tmp_path, monkeypatch):
    settings = Config(tmp_path / "config.json")
    settings.update(
        accounts=["alice", "bob"], default_account="alice",
        auto_login=True, auto_login_accounts=["alice", "bob"],
    )
    secrets = {"alice": "pass-one", "bob": "pass-two"}
    monkeypatch.setattr("gttrl.credentials.Accounts.get", lambda self, username: secrets[username])
    auth_calls, launched, updates = [], [], []

    class FakeAuth:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def login(self, username, password, **kwargs):
            auth_calls.append((username, password))
            return LoginResponse(f"cookie-{username}", "host", "/content/patchmanifest.txt")

    class FakeProcess:
        def poll(self):
            return None

    async def update(self, manifest, *, show_progress=True):
        updates.append(manifest)

    def launch(self, cookie, server):
        launched.append((cookie, server))
        return FakeProcess()

    monkeypatch.setattr("gttrl.cli.AuthClient", FakeAuth)
    monkeypatch.setattr("gttrl.cli.Updater.update", update)
    monkeypatch.setattr("gttrl.cli.Launcher.launch_game", launch)
    monkeypatch.setattr("gttrl.cli.time.sleep", lambda seconds: None)

    result = CliRunner().invoke(main, ["play", "--config-path", str(settings.path)])
    assert result.exit_code == 0, result.output
    assert auth_calls == [("alice", "pass-one"), ("bob", "pass-two")]
    assert updates == ["/content/patchmanifest.txt"]
    assert launched == [("cookie-alice", "host"), ("cookie-bob", "host")]

    auth_calls.clear()
    launched.clear()
    result = CliRunner().invoke(
        main, ["play", "--config-path", str(settings.path), "--account", "bob", "--skip-update"]
    )
    assert result.exit_code == 0, result.output
    assert auth_calls == [("bob", "pass-two")]
    assert launched == [("cookie-bob", "host")]


def test_mismatched_multi_login_manifests_fail_before_launch(tmp_path, monkeypatch):
    settings = Config(tmp_path / "config.json")
    settings.update(
        accounts=["alice", "bob"], auto_login=True,
        auto_login_accounts=["alice", "bob"],
    )
    monkeypatch.setattr("gttrl.credentials.Accounts.get", lambda self, user: "pw")

    class FakeAuth:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def login(self, username, password, **kwargs):
            return LoginResponse(username, "host", f"/content/{username}.json")

    monkeypatch.setattr("gttrl.cli.AuthClient", FakeAuth)
    monkeypatch.setattr(
        "gttrl.cli.Launcher.launch_game",
        lambda *args: pytest.fail("Should not launch with inconsistent manifests"),
    )
    result = CliRunner().invoke(main, ["play", "--config-path", str(settings.path)])
    assert result.exit_code != 0
    assert "different patch manifests" in result.output


def test_rejected_saved_password_prompts_and_updates_keyring(tmp_path, monkeypatch):
    config = Config(tmp_path / "config.json")
    config.update(accounts=["alice"], default_account="alice")
    accounts = Accounts(config)

    class FakeAuth:
        def __init__(self):
            self.attempts = []

        def login(self, username, password, **kwargs):
            self.attempts.append(password)
            if password == "old":
                raise LoginRejected("Invalid credentials")
            return LoginResponse("new-cookie", "host")

    responses = iter(["retry", "yes"])
    updated = []
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr("gttrl.cli._select", lambda *args: next(responses))
    monkeypatch.setattr("gttrl.cli._prompt_text", lambda *args, **kwargs: "new")
    monkeypatch.setattr(
        accounts, "update_password", lambda username, password: updated.append((username, password))
    )
    auth = FakeAuth()
    assert _authenticate(auth, accounts, config, "alice", "old", True).play_cookie == "new-cookie"
    assert auth.attempts == ["old", "new"]
    assert updated == [("alice", "new")]


def test_network_failure_does_not_offer_to_replace_password(tmp_path, monkeypatch):
    config = Config(tmp_path / "config.json")
    config.set("accounts", ["alice"])
    accounts = Accounts(config)

    class FakeAuth:
        def login(self, username, password, **kwargs):
            raise LoginError("Server unavailable")

    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr(
        "gttrl.cli._select",
        lambda *args: pytest.fail("Network errors should not prompt for new passwords"),
    )
    with pytest.raises(LoginError, match="Server unavailable"):
        _authenticate(FakeAuth(), accounts, config, "alice", "old", True)


def test_skip_rejected_saved_account(tmp_path, monkeypatch):
    config = Config(tmp_path / "config.json")
    config.set("accounts", ["alice"])

    class FakeAuth:
        def login(self, username, password, **kwargs):
            raise LoginRejected("Rejected")

    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr("gttrl.cli._select", lambda *args: "skip")
    assert _authenticate(FakeAuth(), Accounts(config), config, "alice", "pw", True) is None


@pytest.mark.parametrize(
    ("choice", "expected", "default"),
    [
        ("exclusive", ["bob"], "bob"),
        ("add", ["alice", "bob"], "alice"),
        ("save", ["alice"], "alice"),
    ],
)
def test_second_account_add_prompt_choices(
    tmp_path, monkeypatch, choice, expected, default
):
    settings = Config(tmp_path / "config.json")
    settings.update(
        accounts=["alice"], default_account="alice",
        auto_login=True, auto_login_accounts=["alice"],
    )
    saved = []
    selected_choices = []

    class Auth:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def login(self, username, password, **kwargs):
            assert username == "bob"
            return LoginResponse("cookie", "server")

    def select(message, choices):
        selected_choices.extend(choices)
        return choice

    monkeypatch.setattr("gttrl.cli.AuthClient", Auth)
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr("gttrl.cli._select", select)
    monkeypatch.setattr(
        "gttrl.cli._prompt_text",
        lambda message, *, password=False: "password",
    )
    monkeypatch.setattr("gttrl.credentials.Accounts._check_backend", lambda *args: None)
    monkeypatch.setattr(
        "gttrl.credentials.keyring.set_password",
        lambda service, username, password: saved.append((username, password)),
    )
    result = CliRunner().invoke(
        main,
        [
            "accounts", "--config-path", str(settings.path), "add",
            "--username", "bob",
        ],
    )
    # Password input is mocked so the test does not need a real TTY.
    assert result.exit_code == 0, result.output
    assert [value for _, value in selected_choices] == [
        "exclusive", "add", "save",
    ]
    assert saved and saved[0][0] == "bob"
    fresh = Config(settings.path)
    assert fresh.get("auto_login_accounts") == expected
    assert fresh.get("default_account") == default


@pytest.mark.parametrize(
    ("choice", "expected", "default"),
    [
        ("exclusive", ["bob"], "bob"),
        ("add", ["alice", "bob"], "alice"),
        ("save", ["alice"], "alice"),
        ("no", ["alice"], "alice"),
    ],
)
def test_remember_second_account_login_prompt(
    tmp_path, monkeypatch, choice, expected, default
):
    settings = Config(tmp_path / "config.json")
    settings.update(
        accounts=["alice"], default_account="alice",
        auto_login=True, auto_login_accounts=["alice"],
    )
    accounts = Accounts(settings)
    seen = []
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr(
        "gttrl.cli._select",
        lambda message, choices: seen.extend(choices) or choice,
    )
    monkeypatch.setattr("gttrl.credentials.Accounts._check_backend", lambda *args: None)
    monkeypatch.setattr("gttrl.credentials.keyring.set_password", lambda *args: None)
    _ask_save(settings, accounts, "bob", "secret")
    assert [value for _, value in seen] == [
        "exclusive", "add", "save", "no", "never"
    ]
    fresh = Config(settings.path)
    assert fresh.get("auto_login_accounts") == expected
    assert fresh.get("default_account") == default
    assert ("bob" in fresh.get("accounts")) == (choice != "no")


def test_exclusive_and_auto_login_options_conflict(tmp_path):
    path = tmp_path / "config.json"
    result = CliRunner().invoke(
        main, [
            "accounts", "--config-path", str(path), "add",
            "--username", "bob", "--exclusive-auto-login", "--auto-login",
        ]
    )
    assert result.exit_code == 2
    assert "cannot be combined" in result.output


@pytest.mark.parametrize(
    ("flag", "expected", "default"),
    [
        ("--exclusive-auto-login", ["bob"], "bob"),
        ("--auto-login", ["alice", "bob"], "alice"),
        ("--no-auto-login", ["alice"], "alice"),
    ],
)
def test_accounts_add_explicit_modes_noninteractive(
    tmp_path, monkeypatch, flag, expected, default
):
    config = Config(tmp_path / "config.json")
    config.update(
        accounts=["alice"], default_account="alice",
        auto_login=True, auto_login_accounts=["alice"],
    )

    class FakeAuth:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def login(self, username, password, **kwargs):
            return LoginResponse("cookie", "server")

    monkeypatch.setattr("gttrl.cli.AuthClient", FakeAuth)
    monkeypatch.setattr("gttrl.cli._interactive", lambda: False)
    monkeypatch.setattr(
        "gttrl.cli._prompt_text",
        lambda message, *, password=False: "new-password",
    )
    monkeypatch.setattr("gttrl.credentials.Accounts._check_backend", lambda *args: None)
    monkeypatch.setattr("gttrl.credentials.keyring.set_password", lambda *args: None)
    result = CliRunner().invoke(
        main, [
            "accounts", "--config-path", str(config.path), "add",
            "--username", "bob", flag,
        ]
    )
    assert result.exit_code == 0, result.output
    actual = Config(config.path)
    assert actual.get("auto_login_accounts") == expected
    assert actual.get("default_account") == default
