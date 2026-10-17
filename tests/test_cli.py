import pytest
from click.testing import CliRunner

from gttrl.cli import _ask_save, main
from gttrl.config import Config
from gttrl.credentials import Accounts


def test_default_play_and_explicit_play():
    runner = CliRunner()
    for prefix in ([], ["play"]):
        result = runner.invoke(main, [
            *prefix, "--no-config-file", "--skip-update",
            "--play-cookie", "abc", "--game-server", "server",
            "--print-play-cookie-and-game-server",
        ])
        assert result.exit_code == 0, result.output
        assert "Play cookie: abc" in result.output


def test_conflicting_modes():
    result = CliRunner().invoke(main, [
        "play", "-n", "--skip-update", "--username", "toon",
        "--play-cookie", "token", "--game-server", "server",
    ])
    assert result.exit_code == 2
    assert "cannot be combined" in result.output


def test_config_commands(tmp_path):
    config = str(tmp_path / "config.json")
    runner = CliRunner()
    result = runner.invoke(main, ["config", "--config-path", config, "set", "concurrent-downloads", "4"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(main, ["config", "--config-path", config, "get", "concurrent-downloads"])
    assert result.output.strip() == "4"


@pytest.mark.parametrize(
    ("args", "expected_prompts"),
    [
        (["--play-cookie", "existing-cookie"], [("Game server", False)]),
        (["--game-server", "existing-server"], [("Play cookie", True)]),
        (["--ask-play-cookie"], [("Play cookie", True), ("Game server", False)]),
        (["--ask-play-cookie", "--game-server", "existing-server"], [("Play cookie", True)]),
    ],
)
def test_missing_session_values_are_prompted(monkeypatch, args, expected_prompts):
    prompts = []

    def fake_prompt(message, *, password=False):
        prompts.append((message, password))
        return {"Play cookie": "prompted-cookie", "Game server": "prompted-server"}[message]

    monkeypatch.setattr("gttrl.cli._prompt_text", fake_prompt)
    result = CliRunner().invoke(
        main, ["play", "--no-config-file", *args, "--print-play-cookie-and-game-server"]
    )
    assert result.exit_code == 0, result.output
    assert prompts == expected_prompts
    assert "Play cookie: " + (
        "existing-cookie" if "--play-cookie" in args else "prompted-cookie"
    ) in result.output
    assert "Game server: " + (
        "existing-server" if "--game-server" in args else "prompted-server"
    ) in result.output


@pytest.mark.parametrize(
    ("args", "missing"),
    [
        (["--play-cookie", "cookie"], "Game server"),
        (["--game-server", "host"], "Play cookie"),
        (["--ask-play-cookie"], "Play cookie"),
    ],
)
def test_missing_session_values_without_terminal_fail_clearly(args, missing):
    result = CliRunner().invoke(main, ["play", "-n", *args])
    assert result.exit_code != 0
    assert f"{missing} is required in non-interactive mode" in result.output


def test_session_mode_rejects_account_options_before_prompt(monkeypatch):
    monkeypatch.setattr(
        "gttrl.cli._prompt_text",
        lambda *args, **kwargs: pytest.fail("Must reject mixed authentication first"),
    )
    result = CliRunner().invoke(
        main, ["play", "-n", "--ask-play-cookie", "--username", "toon"]
    )
    assert result.exit_code == 2
    assert "cannot be combined" in result.output


def test_ask_play_cookie_is_visible_and_session_needs_no_extra_prompt(monkeypatch):
    monkeypatch.setattr(
        "gttrl.cli._prompt_text",
        lambda *args, **kwargs: pytest.fail("Session is fully provided"),
    )
    runner = CliRunner()
    help_result = runner.invoke(main, ["play", "--help"])
    assert "--ask-play-cookie" in help_result.output
    assert "--login-mode" not in help_result.output
    result = runner.invoke(
        main,
        [
            "-n",
            "--play-cookie", "cookie",
            "--game-server", "server",
            "--print-play-cookie-and-game-server",
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.output == "Play cookie: cookie\nGame server: server\n"


def test_explicit_flags_override_saved_settings(tmp_path, monkeypatch):
    settings = Config(tmp_path / "config.json")
    settings.set("skip_update", True)
    settings.set("display_game_log", True)
    updated = []
    launched = []

    async def update(self, manifest, *, show_progress=True):
        updated.append(manifest)

    def launch(self, cookie, server):
        launched.append((cookie, server, self.display_game_log))

    monkeypatch.setattr("gttrl.cli.Updater.update", update)
    monkeypatch.setattr("gttrl.cli.Launcher.launch_game", launch)
    args = [
        "--config-path", str(settings.path), "--play-cookie", "abc",
        "--game-server", "server", "--hide-game-log",
    ]
    result = CliRunner().invoke(main, ["play", *args, "--check-update"])
    assert result.exit_code == 0, result.output
    assert updated == [None]
    assert launched == [("abc", "server", False)]

    updated.clear()
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 0, result.output
    assert updated == []  # stored skip_update setting remains effective


def test_declining_remember_account_skips_all_wizard_questions(tmp_path, monkeypatch):
    settings = Config(tmp_path / "config.json")
    saved = Accounts(settings)
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    questions = []
    monkeypatch.setattr(
        "gttrl.cli._yes_no",
        lambda question: questions.append(question) or False,
    )
    monkeypatch.setattr(
        "gttrl.cli._prompt_optional_alias",
        lambda: pytest.fail("Do not prompt for alias after No"),
    )
    monkeypatch.setattr(saved, "add", lambda *args, **kwargs: pytest.fail("Should not save"))
    _ask_save(settings, saved, "toon", "password")
    assert Config(settings.path).get("account_wizard") is True
    assert questions == ["Remember this account?"]


def test_ask_play_cookie_config_prompts_and_command_line_overrides(tmp_path, monkeypatch):
    settings = Config(tmp_path / "config.json")
    settings.set("ask_play_cookie", True)
    prompts = []

    def prompt(message, *, password=False):
        prompts.append(message)
        return {
            "Play cookie": "from-prompt",
            "Game server": "game-host",
            "Username": "toon",
            "Password": "pw",
        }[message]

    monkeypatch.setattr("gttrl.cli._prompt_text", prompt)
    runner = CliRunner()
    command = [
        "play", "--config-path", str(settings.path),
        "--print-play-cookie-and-game-server",
    ]
    result = runner.invoke(main, command)
    assert result.exit_code == 0, result.output
    assert prompts == ["Play cookie", "Game server"]
    assert result.output == "Play cookie: from-prompt\nGame server: game-host\n"

    class FakeAuth:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def login(self, username, password, **kwargs):
            from gttrl.models import LoginResponse

            return LoginResponse("credentials-cookie", "credentials-server")

    monkeypatch.setattr("gttrl.cli.AuthClient", FakeAuth)
    prompts.clear()
    result = runner.invoke(main, [*command, "--no-ask-play-cookie", "--username", "toon", "--password", "pw"])
    assert result.exit_code == 0, (result.output, result.exception)
    assert not prompts
    assert result.output == "Play cookie: credentials-cookie\nGame server: credentials-server\n"
    assert Config(settings.path).get("ask_play_cookie") is True


def test_configured_cookie_mode_is_overridden_by_explicit_account_credentials(tmp_path, monkeypatch):
    settings = Config(tmp_path / "config.json")
    settings.set("ask_play_cookie", True)
    seen = []

    class FakeAuth:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def login(self, username, password, **kwargs):
            seen.append((username, password))
            from gttrl.models import LoginResponse

            return LoginResponse("cookie", "server")

    monkeypatch.setattr("gttrl.cli.AuthClient", FakeAuth)
    monkeypatch.setattr(
        "gttrl.cli._prompt_text",
        lambda *args, **kwargs: pytest.fail("Explicit username and password must not prompt"),
    )
    result = CliRunner().invoke(main, [
        "--config-path", str(settings.path),
        "--username", "toon@example.com", "--password", "secret",
        "--print-play-cookie-and-game-server",
    ])
    assert result.exit_code == 0, (result.output, result.exception)
    assert seen == [("toon@example.com", "secret")]
    assert result.output.endswith("Play cookie: cookie\nGame server: server\n")
    assert "GTTRL 2.0" not in result.output


def test_cookie_cli_overrides_config_false_even_when_both_values_supplied(tmp_path):
    settings = Config(tmp_path / "config.json")
    settings.set("ask_play_cookie", False)
    result = CliRunner().invoke(main, [
        "--config-path", str(settings.path),
        "--play-cookie", "cookie", "--game-server", "server",
        "--print-play-cookie-and-game-server",
    ])
    assert result.exit_code == 0, result.output
    assert result.output == "Play cookie: cookie\nGame server: server\n"


def test_explicit_cookie_mode_rejects_mixed_account_inputs_even_with_config(tmp_path):
    settings = Config(tmp_path / "config.json")
    settings.set("ask_play_cookie", True)
    result = CliRunner().invoke(main, [
        "--config-path", str(settings.path),
        "--ask-play-cookie", "--username", "toon",
    ])
    assert result.exit_code == 2
    assert "cannot be combined" in result.output


def test_play_cookie_preference_is_reset_with_other_preferences(tmp_path):
    settings = Config(tmp_path / "config.json")
    settings.set("ask_play_cookie", True)
    result = CliRunner().invoke(main, [
        "config", "--config-path", str(settings.path), "reset", "--yes",
    ])
    assert result.exit_code == 0, result.output
    assert Config(settings.path).get("ask_play_cookie") is False


def test_play_banner_not_printed_in_machine_readable_config_or_cookie_results(tmp_path):
    settings = Config(tmp_path / "config.json")
    runner = CliRunner()
    config_result = runner.invoke(main, ["config", "--config-path", str(settings.path), "show"])
    assert config_result.exit_code == 0
    assert "GTTRL 2.0" not in config_result.output
    cookie_result = runner.invoke(main, [
        "--config-path", str(settings.path),
        "--play-cookie", "cookie", "--game-server", "server",
        "--print-play-cookie-and-game-server",
    ])
    assert cookie_result.exit_code == 0
    assert "GTTRL 2.0" not in cookie_result.output
