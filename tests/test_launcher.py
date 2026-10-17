import os
import subprocess

import click
import pytest
from click.testing import CliRunner

from gttrl.cli import main
from gttrl.launcher import Launcher


def test_launcher_starts_separate_processes_without_mutating_parent_env(tmp_path, monkeypatch):
    (tmp_path / Launcher.executable()).touch()
    calls = []
    dummy = object()

    def popen(args, **kwargs):
        calls.append((args, kwargs))
        return dummy

    monkeypatch.setattr(subprocess, "Popen", popen)
    before = os.environ.get("TTR_PLAYCOOKIE")
    launcher = Launcher(tmp_path)
    assert launcher.launch_game("first-cookie", "server") is dummy
    assert launcher.launch_game("second-cookie", "server") is dummy
    assert [kwargs["env"]["TTR_PLAYCOOKIE"] for _, kwargs in calls] == [
        "first-cookie", "second-cookie"
    ]
    assert os.environ.get("TTR_PLAYCOOKIE") == before
    assert all(kwargs["cwd"] == tmp_path for _, kwargs in calls)


def test_launcher_spawn_errors_are_user_friendly(tmp_path, monkeypatch):
    (tmp_path / Launcher.executable()).touch()

    def popen(*args, **kwargs):
        raise OSError("missing shared library")

    monkeypatch.setattr(subprocess, "Popen", popen)
    with pytest.raises(click.ClickException, match="missing shared library"):
        Launcher(tmp_path).launch_game("cookie", "server")


def test_visible_game_log_reports_nonzero_game_exit(tmp_path, monkeypatch):
    class FakeProcess:
        def wait(self):
            return 23

    monkeypatch.setattr(
        "gttrl.cli.Launcher.launch_game",
        lambda *args: FakeProcess(),
    )
    result = CliRunner().invoke(main, [
        "play", "-n", "--skip-update", "--display-game-log",
        "--play-cookie", "cookie", "--game-server", "host",
    ])
    assert result.exit_code != 0
    assert "Game exited unsuccessfully" in result.output


def test_detached_game_exiting_immediately_reports_error(monkeypatch):
    class FakeProcess:
        def poll(self):
            return 23

    monkeypatch.setattr("gttrl.cli.Launcher.launch_game", lambda *args: FakeProcess())
    monkeypatch.setattr("gttrl.cli.time.sleep", lambda *_: None)
    result = CliRunner().invoke(main, [
        "play", "-n", "--skip-update",
        "--play-cookie", "cookie", "--game-server", "host",
    ])
    assert result.exit_code != 0
    assert "Game closed immediately" in result.output
    assert "--display-game-log" in result.output
