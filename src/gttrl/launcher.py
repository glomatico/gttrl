"""Start the Toontown Rewritten game client."""

from __future__ import annotations

import os
import platform
import stat
import subprocess
import sys
from pathlib import Path

import click


class Launcher:
    def __init__(self, game_dir_path: Path, display_game_log: bool = False):
        self.game_dir_path = Path(game_dir_path).expanduser()
        self.display_game_log = display_game_log

    @staticmethod
    def executable() -> str:
        if sys.platform == "win32":
            return "TTREngine64.exe" if platform.architecture()[0] == "64bit" else "TTREngine.exe"
        if sys.platform == "darwin":
            return "Toontown Rewritten"
        if sys.platform.startswith("linux"):
            return "TTREngine"
        raise click.ClickException(f"Unsupported operating system: {sys.platform}")

    def launch_game(self, play_cookie: str, game_server: str) -> subprocess.Popen:
        executable = self.game_dir_path / self.executable()
        if not executable.is_file():
            raise click.ClickException(f"Game executable not found: {executable}")
        if os.name != "nt":
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        # Keep the user's shell environment and working directory unchanged.
        env = os.environ.copy()
        env.update({"TTR_PLAYCOOKIE": play_cookie, "TTR_GAMESERVER": game_server})
        kwargs = {
            "cwd": self.game_dir_path,
            "env": env,
        }
        if not self.display_game_log:
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            else:
                kwargs["start_new_session"] = True
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
        try:
            return subprocess.Popen(
                [str(executable)],
                **kwargs,
            )
        except OSError as error:
            raise click.ClickException(
                f"Unable to start {executable}: {error}. "
                "Verify that the game files and required system libraries are installed."
            ) from error
