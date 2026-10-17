"""Alias-driven multi-login, wizard overrides, and the interactive account editor."""

import json

import pytest
from click.testing import CliRunner

from gttrl.cli import main
from gttrl.config import Config, _account
from gttrl.credentials import Accounts
from gttrl.models import LoginResponse


def setup_accounts(path):
    settings = Config(path)
    settings.set("accounts", [
        _account("alice@example.com", alias="toon1", auto_launch=True, save_password=True),
        _account("bob@example.com", alias="toon2", auto_launch=True, save_password=True),
    ])
    return settings


def fake_launch(monkeypatch):
    logins, launched, updates = [], [], []

    class FakeAuth:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def login(self, username, password, **_):
            logins.append((username, password))
            return LoginResponse(f"cookie-{username}", "server")

    class FakeProcess:
        def poll(self):
            return None

    async def update(_self, manifest=None, *, show_progress=True):
        updates.append(manifest)

    def launch(_self, cookie, server):
        launched.append((cookie, server))
        return FakeProcess()

    monkeypatch.setattr("gttrl.cli.AuthClient", FakeAuth)
    monkeypatch.setattr("gttrl.cli.Launcher.launch_game", launch)
    monkeypatch.setattr("gttrl.cli.Updater.update", update)
    monkeypatch.setattr("gttrl.cli.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "gttrl.credentials.Accounts.keyring_password",
        lambda self, username: "pw-" + username,
    )
    return logins, launched, updates


@pytest.mark.parametrize("account_tokens", [
    ["--accounts", "toon2", "toon1"],
    ["--accounts", "toon2,toon1"],
    ["--accounts", "toon2", "--accounts", "toon1"],
    ["--accounts", "toon2", "alice@example.com"],
])
def test_explicit_accounts_override_auto_login(
    tmp_path, monkeypatch, account_tokens
):
    settings = setup_accounts(tmp_path / "config.json")
    logins, launched, updates = fake_launch(monkeypatch)
    result = CliRunner().invoke(main, [
        "play", "--config-path", str(settings.path), *account_tokens,
    ])
    assert result.exit_code == 0, (result.output, result.exception)
    assert logins == [
        ("bob@example.com", "pw-bob@example.com"),
        ("alice@example.com", "pw-alice@example.com"),
    ]
    assert len(launched) == 2
    assert updates == [None]


def test_accounts_override_does_not_launch_unselected_account(tmp_path, monkeypatch):
    settings = setup_accounts(tmp_path / "config.json")
    logins, launched, _updates = fake_launch(monkeypatch)
    result = CliRunner().invoke(main, [
        "--config-path", str(settings.path), "--accounts", "toon2", "--skip-update"
    ])
    assert result.exit_code == 0, (result.output, result.exception)
    assert logins == [("bob@example.com", "pw-bob@example.com")]
    assert len(launched) == 1


@pytest.mark.parametrize("names", [
    ["toon1", "alice@example.com"],
    ["toon1", "toon1"],
])
def test_duplicate_account_selection_is_rejected(tmp_path, names):
    settings = setup_accounts(tmp_path / "config.json")
    result = CliRunner().invoke(main, [
        "--config-path", str(settings.path), "--accounts", *names
    ])
    assert result.exit_code != 0
    assert "more than once" in result.output


def test_wizard_disabled_skips_account_setup_but_keeps_saved_autologin(
    tmp_path, monkeypatch
):
    settings = setup_accounts(tmp_path / "config.json")
    settings.set("account_wizard", False)
    logins, launched, _ = fake_launch(monkeypatch)
    monkeypatch.setattr("gttrl.cli._ask_save", lambda *args: pytest.fail("No wizard"))
    result = CliRunner().invoke(main, [
        "--config-path", str(settings.path), "--skip-update",
    ])
    assert result.exit_code == 0, (result.output, result.exception)
    assert len(logins) == len(launched) == 2


def test_disabled_wizard_does_not_register_new_account(
    tmp_path, monkeypatch
):
    settings = Config(tmp_path / "config.json")
    settings.set("account_wizard", False)
    fake_launch(monkeypatch)
    monkeypatch.setattr("gttrl.cli._ask_save", lambda *args: pytest.fail("No wizard"))
    result = CliRunner().invoke(main, [
        "play", "--config-path", str(settings.path),
        "--username", "manual@example.com", "--password", "pass",
        "--skip-update",
    ])
    assert result.exit_code == 0, (result.output, result.exception)
    assert Config(settings.path).get("accounts") == []


def test_disabled_wizard_without_accounts_requires_cli_credentials(tmp_path):
    settings = Config(tmp_path / "config.json")
    settings.set("account_wizard", False)
    result = CliRunner().invoke(main, [
        "--config-path", str(settings.path)
    ])
    assert result.exit_code == 2
    assert "Account wizard is disabled" in result.output


@pytest.mark.parametrize("extra", [[], ["--account-wizard"]])
def test_explicit_username_skips_account_setup_even_if_wizard_enabled(
    tmp_path, monkeypatch, extra
):
    settings = Config(tmp_path / "config.json")
    settings.set("account_wizard", True)
    logins, launched, _ = fake_launch(monkeypatch)
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr(
        "gttrl.cli._ask_save",
        lambda *args: pytest.fail("Explicit --username should bypass setup"),
    )
    result = CliRunner().invoke(main, [
        "--config-path", str(settings.path), *extra,
        "--username", "email@example.com", "--password", "pw",
        "--skip-update",
    ])
    assert result.exit_code == 0, (result.output, result.exception)
    assert logins == [("email@example.com", "pw")]
    assert len(launched) == 1
    assert Config(settings.path).get("account_wizard") is True
    assert Accounts(Config(settings.path)).usernames == []


def test_username_only_prompts_just_for_password_and_never_runs_wizard(
    tmp_path, monkeypatch
):
    settings = Config(tmp_path / "config.json")
    settings.set("ask_play_cookie", True)
    logins, launched, _ = fake_launch(monkeypatch)
    messages = []
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)

    def prompt(message, *, password=False):
        messages.append((message, password))
        return "typed-password"

    monkeypatch.setattr("gttrl.cli._prompt_text", prompt)
    monkeypatch.setattr(
        "gttrl.cli._ask_save",
        lambda *args: pytest.fail("Explicit username must skip the wizard"),
    )
    result = CliRunner().invoke(main, [
        "--config-path", str(settings.path),
        "--username", "new@example.com", "--skip-update",
    ])
    assert result.exit_code == 0, (result.output, result.exception)
    assert messages == [("Password", True)]
    assert logins == [("new@example.com", "typed-password")]
    assert len(launched) == 1
    assert "GTTRL 2.0" in result.output
    assert Accounts(Config(settings.path)).usernames == []


def test_username_with_password_stdin_skips_setup_and_is_not_persisted(
    tmp_path, monkeypatch
):
    settings = Config(tmp_path / "config.json")
    logins, launched, _ = fake_launch(monkeypatch)
    monkeypatch.setattr(
        "gttrl.cli._ask_save",
        lambda *args: pytest.fail("Explicit username must skip the wizard"),
    )
    result = CliRunner().invoke(main, [
        "--config-path", str(settings.path), "--username", "one@example.com",
        "--password-stdin", "--skip-update",
    ], input="password-through-stdin\n")
    assert result.exit_code == 0, (result.output, result.exception)
    assert logins == [("one@example.com", "password-through-stdin")]
    assert len(launched) == 1
    assert Accounts(Config(settings.path)).usernames == []


def test_account_manager_alias_and_auto_login_from_bare_accounts(
    tmp_path, monkeypatch
):
    settings = setup_accounts(tmp_path / "config.json")
    settings.set("account_wizard", False)
    selections = iter(["alice@example.com", "alias", "auto", "disable", "back", "__exit__"])
    monkeypatch.setattr("gttrl.cli._select", lambda *args: next(selections))
    monkeypatch.setattr("gttrl.cli._prompt_optional_alias", lambda: "renamed")
    result = CliRunner().invoke(main, [
        "accounts", "--config-path", str(settings.path),
    ])
    assert result.exit_code == 0, (result.output, result.exception)
    accounts = Accounts(Config(settings.path))
    assert accounts.resolve("renamed") == "alice@example.com"
    assert accounts.auto_launch_accounts == ["bob@example.com"]


def test_account_manager_add_choice_runs_account_setup(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    Config(path).set("account_wizard", False)
    fake_launch(monkeypatch)
    choices = iter(["__add__", "__exit__"])
    monkeypatch.setattr("gttrl.cli._select", lambda *args: next(choices))
    monkeypatch.setattr("gttrl.cli._prompt_text", lambda *args, **kwargs: "pw")
    monkeypatch.setattr("gttrl.cli._prompt_optional_alias", lambda: "toon1")
    monkeypatch.setattr("gttrl.cli._yes_no", lambda *args: False)
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    result = CliRunner().invoke(main, [
        "accounts", "--config-path", str(path)
    ])
    assert result.exit_code == 0, (result.output, result.exception)
    assert Accounts(Config(path)).usernames == []


def test_account_manager_only_password_saving_can_replace_keyring(
    tmp_path, monkeypatch
):
    settings = setup_accounts(tmp_path / "config.json")
    saved = []
    selections = iter(["alice@example.com", "policy", "enable", "yes", "back", "__exit__"])
    menus = []

    def choose(message, options):
        menus.append([value for _, value in options])
        return next(selections)

    monkeypatch.setattr("gttrl.cli._select", choose)
    monkeypatch.setattr("gttrl.cli._prompt_text", lambda *args, **kwargs: "newsecret")
    monkeypatch.setattr("gttrl.credentials.Accounts._check_backend", lambda *args: None)
    monkeypatch.setattr(
        "gttrl.credentials.keyring.set_password",
        lambda _service, username, password: saved.append((username, password)),
    )

    class FakeAuth:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def login(self, username, password, **kwargs):
            assert password == "newsecret"
            return LoginResponse("token", "server")

    monkeypatch.setattr("gttrl.cli.AuthClient", FakeAuth)
    result = CliRunner().invoke(main, ["accounts", "--config-path", str(settings.path)])
    assert result.exit_code == 0, (result.output, result.exception)
    assert "save/overwrite" in result.output
    assert "password" not in menus[1]
    assert saved == [("alice@example.com", "newsecret")]
    assert Accounts(Config(settings.path)).account("toon1")["save_password"] is True


def test_manager_disable_password_saving_and_back(tmp_path, monkeypatch):
    settings = setup_accounts(tmp_path / "config.json")
    deleted = []
    monkeypatch.setattr("gttrl.credentials.Accounts._check_backend", lambda *args: None)
    monkeypatch.setattr(
        "gttrl.credentials.keyring.delete_password",
        lambda service, username: deleted.append(username),
    )
    selections = iter([
        "alice@example.com", "policy", "back", "policy", "disable",
        "auto", "back", "back", "__exit__",
    ])
    monkeypatch.setattr("gttrl.cli._select", lambda *args: next(selections))
    result = CliRunner().invoke(main, ["accounts", "--config-path", str(settings.path)])
    assert result.exit_code == 0, (result.output, result.exception)
    records = Accounts(Config(settings.path))
    assert records.account("toon1")["save_password"] is False
    assert records.account("toon1")["auto_launch"] is True
    assert deleted == ["alice@example.com"]


def test_manager_enabling_password_saving_verifies_then_writes(
    tmp_path, monkeypatch
):
    settings = setup_accounts(tmp_path / "config.json")
    records = settings.get("accounts")
    records[0]["save_password"] = False
    settings.set("accounts", records)
    saved = []
    monkeypatch.setattr("gttrl.credentials.Accounts._check_backend", lambda *args: None)
    monkeypatch.setattr(
        "gttrl.credentials.keyring.set_password",
        lambda service, username, password: saved.append((username, password)),
    )
    monkeypatch.setattr("gttrl.cli._prompt_text", lambda *args, **kwargs: "newpass")
    selections = iter([
        "alice@example.com", "policy", "enable", "yes", "back", "__exit__"
    ])
    monkeypatch.setattr("gttrl.cli._select", lambda *args: next(selections))

    class FakeAuth:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def login(self, username, password, **kwargs):
            assert username == "alice@example.com"
            assert password == "newpass"
            return LoginResponse("cookie", "host")

    monkeypatch.setattr("gttrl.cli.AuthClient", FakeAuth)
    result = CliRunner().invoke(main, ["accounts", "--config-path", str(settings.path)])
    assert result.exit_code == 0, (result.output, result.exception)
    assert Accounts(Config(settings.path)).account("toon1")["save_password"] is True
    assert saved == [("alice@example.com", "newpass")]


def test_first_account_add_prompts_for_alias(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    fake_launch(monkeypatch)
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr("gttrl.cli._prompt_text", lambda *args, **kwargs: "pw")
    monkeypatch.setattr("gttrl.cli._prompt_optional_alias", lambda: "toon1")
    monkeypatch.setattr("gttrl.cli._yes_no", lambda question: question != "Remember the password?")
    result = CliRunner().invoke(main, [
        "accounts", "--config-path", str(path), "add", "--username", "alice@example.com"
    ])
    assert result.exit_code == 0, (result.output, result.exception)
    assert Accounts(Config(path)).account("toon1")["alias"] == "toon1"
    assert Accounts(Config(path)).account("toon1")["auto_launch"] is True
    assert Accounts(Config(path)).account("toon1")["save_password"] is False


def test_old_2_0_accounts_are_not_migrated(tmp_path):
    path = tmp_path / "config.json"
    original = {
        "save_prompt": "never",
        "default_account": "long@example.com",
        "accounts": [{
            "username": "long@example.com",
            "nickname": "Red Toon",
            "auto_login": True,
            "save_password": "yes",
        }],
    }
    path.write_text(json.dumps(original))
    with pytest.raises(Exception, match="Each account must contain"):
        Config(path)
