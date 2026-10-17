"""Multi-toon startup and account setup regression coverage."""

import pytest
from click.testing import CliRunner

from gttrl.auth import LoginError, LoginRejected
from gttrl.cli import _ask_save, _authenticate, main
from gttrl.config import Config, _account
from gttrl.credentials import Accounts
from gttrl.models import LoginResponse


def make_accounts(path, users=("alice", "bob"), selected=("alice",)):
    config = Config(path)
    config.set("accounts", [
        _account(user, auto_launch=user in selected, save_password=True)
        for user in users
    ])
    return config


def test_auto_launch_commands_with_legacy_alias(tmp_path):
    path = tmp_path / "config.json"
    make_accounts(path, users=("alice", "bob", "charlie"), selected=())
    runner = CliRunner()

    def invoke(command, *args):
        return runner.invoke(
            main, ["accounts", "--config-path", str(path), command, *args]
        )

    assert invoke("auto-launch", "set", "alice", "bob").exit_code == 0
    assert invoke("auto-launch", "list").output == "alice\nbob\n"
    assert Accounts(Config(path)).auto_launch_accounts == ["alice", "bob"]
    listed = invoke("list")
    assert "alice (auto-launch)" in listed.output
    assert "charlie" in listed.output
    assert invoke("auto-login", "off").exit_code == 0
    assert Accounts(Config(path)).auto_launch_accounts == []
    assert invoke("auto-launch", "on").exit_code == 0
    assert Accounts(Config(path)).auto_launch_accounts == ["alice"]
    invalid = invoke("auto-launch", "set", "nonexistent")
    assert invalid.exit_code != 0
    assert Accounts(Config(path)).auto_launch_accounts == ["alice"]


def test_interactive_auto_launch_selection(tmp_path, monkeypatch):
    config = make_accounts(tmp_path / "config.json")
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
        main, ["accounts", "--config-path", str(config.path), "auto-launch"]
    )
    assert result.exit_code == 0, result.output
    assert [choice.checked for choice in captured["choices"]] == [True, False]
    assert Accounts(Config(config.path)).auto_launch_accounts == ["alice", "bob"]


def test_multi_launch_updates_once_and_spawns_distinct_games(tmp_path, monkeypatch):
    config = make_accounts(tmp_path / "config.json", selected=("alice", "bob"))
    secrets = {"alice": "pass-one", "bob": "pass-two"}
    monkeypatch.setattr(
        "gttrl.credentials.Accounts.keyring_password",
        lambda self, username: secrets[username],
    )
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

    result = CliRunner().invoke(main, ["play", "--config-path", str(config.path)])
    assert result.exit_code == 0, result.output
    assert auth_calls == [("alice", "pass-one"), ("bob", "pass-two")]
    assert updates == ["/content/patchmanifest.txt"]
    assert launched == [("cookie-alice", "host"), ("cookie-bob", "host")]

    auth_calls.clear()
    launched.clear()
    result = CliRunner().invoke(
        main, ["play", "--config-path", str(config.path), "--account", "bob", "--skip-update"]
    )
    assert result.exit_code == 0, result.output
    assert auth_calls == [("bob", "pass-two")]
    assert launched == [("cookie-bob", "host")]


def test_multi_launch_rejects_inconsistent_manifests(tmp_path, monkeypatch):
    config = make_accounts(tmp_path / "config.json", selected=("alice", "bob"))
    monkeypatch.setattr(
        "gttrl.credentials.Accounts.keyring_password",
        lambda self, user: "pw",
    )

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
        lambda *args: pytest.fail("Cannot launch inconsistent game versions"),
    )
    result = CliRunner().invoke(main, ["play", "--config-path", str(config.path)])
    assert result.exit_code != 0
    assert "different patch manifests" in result.output


def test_rejected_saved_password_can_be_skipped(tmp_path, monkeypatch):
    config = make_accounts(tmp_path / "config.json", users=("alice",))

    class FakeAuth:
        def login(self, username, password, **kwargs):
            raise LoginRejected("Rejected")

    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr("gttrl.cli._select", lambda *args: "skip")
    assert _authenticate(FakeAuth(), Accounts(config), config, "alice", "pw", True) is None


def test_network_failure_does_not_ask_to_replace_password(tmp_path, monkeypatch):
    config = make_accounts(tmp_path / "config.json", users=("alice",))

    class FakeAuth:
        def login(self, username, password, **kwargs):
            raise LoginError("Server unavailable")

    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr(
        "gttrl.cli._select",
        lambda *args: pytest.fail("Network errors must not be considered password rejection"),
    )
    with pytest.raises(LoginError, match="Server unavailable"):
        _authenticate(FakeAuth(), Accounts(config), config, "alice", "pw", True)


@pytest.mark.parametrize(
    ("remember", "auto_launch", "save_password"),
    [
        (False, False, False),
        (True, False, False),
        (True, True, False),
        (True, False, True),
        (True, True, True),
    ],
)
def test_setup_wizard_yes_no_flow(
    tmp_path, monkeypatch, remember, auto_launch, save_password
):
    config = make_accounts(tmp_path / "config.json", users=("alice",))
    accounts = Accounts(config)
    asked = []
    answers = iter([remember, auto_launch, save_password])
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)

    def answer(question):
        asked.append(question)
        return next(answers)

    monkeypatch.setattr("gttrl.cli._yes_no", answer)
    monkeypatch.setattr(
        "gttrl.cli._prompt_optional_alias",
        lambda: "toon2" if remember else pytest.fail("Alias must be skipped"),
    )
    monkeypatch.setattr("gttrl.credentials.Accounts._check_backend", lambda *args: None)
    saved = []
    monkeypatch.setattr(
        "gttrl.credentials.keyring.set_password",
        lambda service, name, password: saved.append((name, password)),
    )
    _ask_save(config, accounts, "bob", "secret")
    if not remember:
        assert asked == ["Remember this account?"]
        assert accounts.usernames == ["alice"]
    else:
        assert asked == [
            "Remember this account?",
            "Enable auto-launch?",
            "Remember the password?",
        ]
        assert accounts.account("toon2")["auto_launch"] is auto_launch
        assert accounts.account("toon2")["save_password"] is save_password
    assert bool(saved) is bool(remember and save_password)


def test_noninteractive_account_add_respects_boolean_flags(tmp_path, monkeypatch):
    config = make_accounts(tmp_path / "config.json", users=("alice",))

    class FakeAuth:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def login(self, username, password, **kwargs):
            return LoginResponse("cookie", "server")

    monkeypatch.setattr("gttrl.cli.AuthClient", FakeAuth)
    monkeypatch.setattr("gttrl.cli._interactive", lambda: False)
    monkeypatch.setattr("gttrl.cli._prompt_text", lambda *args, **kwargs: "new-password")
    result = CliRunner().invoke(
        main, [
            "accounts", "--config-path", str(config.path), "add",
            "--username", "bob", "--alias", "toon2",
            "--auto-launch", "--no-save-password",
        ],
    )
    assert result.exit_code == 0, result.output
    saved = Accounts(Config(config.path))
    assert saved.account("toon2")["auto_launch"] is True
    assert saved.account("toon2")["save_password"] is False
