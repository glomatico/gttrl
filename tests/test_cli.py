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


def test_legacy_login_mode():
    result = CliRunner().invoke(main, [
        "--no-config-file", "--login-mode", "playcookieandgameserver",
        "--play-cookie", "abc", "--game-server", "host",
        "--print-play-cookie-and-game-server",
    ])
    assert result.exit_code == 0, result.output
    assert "legacy mode name" in result.output


@pytest.mark.parametrize(
    ("args", "expected_prompts"),
    [
        (["--play-cookie", "existing-cookie"], [("Game server", False)]),
        (["--game-server", "existing-server"], [("Play cookie", True)]),
        (["--login-mode", "play-cookie"], [("Play cookie", True), ("Game server", False)]),
        (["--login-mode", "play-cookie", "--game-server", "existing-server"], [("Play cookie", True)]),
        (["--login-mode", "playcookieandgameserver"], [("Play cookie", True), ("Game server", False)]),
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
        (["--login-mode", "play-cookie"], "Play cookie"),
    ],
)
def test_missing_session_values_without_terminal_fail_clearly(args, missing):
    result = CliRunner().invoke(main, ["play", "-n", *args])
    assert result.exit_code != 0
    assert f"{missing} is required in non-interactive mode" in result.output


def test_explicit_credentials_mode_rejects_session_options():
    result = CliRunner().invoke(
        main, ["play", "-n", "--login-mode", "credentials", "--play-cookie", "cookie"]
    )
    assert result.exit_code == 2
    assert "Credential login cannot use" in result.output


def test_session_mode_rejects_account_options_before_prompt(monkeypatch):
    monkeypatch.setattr(
        "gttrl.cli._prompt_text",
        lambda *args, **kwargs: pytest.fail("Must reject mixed authentication first"),
    )
    result = CliRunner().invoke(
        main, ["play", "-n", "--login-mode", "play-cookie", "--username", "toon"]
    )
    assert result.exit_code == 2
    assert "cannot be combined" in result.output


def test_login_mode_is_visible_and_fully_specified_session_needs_no_prompt(monkeypatch):
    monkeypatch.setattr(
        "gttrl.cli._prompt_text",
        lambda *args, **kwargs: pytest.fail("Session is fully provided"),
    )
    runner = CliRunner()
    help_result = runner.invoke(main, ["play", "--help"])
    assert "--login-mode" in help_result.output
    assert "play-cookie" in help_result.output
    result = runner.invoke(
        main,
        [
            "-n",
            "--login-mode", "play-cookie",
            "--play-cookie", "cookie",
            "--game-server", "server",
            "--print-play-cookie-and-game-server",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Play cookie: cookie\nGame server: server" in result.output


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
