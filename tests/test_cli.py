from click.testing import CliRunner

from gttrl.cli import main


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
