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
    assert "deprecated" in result.output


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


def test_never_ask_again_is_persistent(tmp_path, monkeypatch):
    settings = Config(tmp_path / "config.json")
    saved = Accounts(settings)
    monkeypatch.setattr("gttrl.cli._interactive", lambda: True)
    monkeypatch.setattr("gttrl.cli._select", lambda *args: "never")
    monkeypatch.setattr(saved, "add", lambda *args, **kwargs: pytest.fail("Should not save"))
    _ask_save(settings, saved, "toon", "password")
    assert Config(settings.path).get("save_prompt") == "never"
