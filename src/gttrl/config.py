"""Non-secret launcher preferences. Passwords never belong in this file."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import click

from .constants import config_path, game_dir

DEFAULTS: dict[str, Any] = {
    "game_dir_path": str(game_dir()),
    "display_game_log": False,
    "skip_update": False,
    "concurrent_downloads": 3,
    "accounts": [],
    "default_account": None,
    "auto_login": False,
    "auto_login_accounts": [],
    "save_prompt": "ask",
}


def _validate(key: str, value: Any) -> Any:
    if key not in DEFAULTS:
        raise click.ClickException(f"Unknown setting: {key}")
    if key in {"accounts", "auto_login_accounts"}:
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ) or len(set(value)) != len(value):
            raise click.ClickException(f"{key} must be a list of unique usernames")
    elif key in {"display_game_log", "skip_update", "auto_login"}:
        if not isinstance(value, bool):
            raise click.ClickException(f"{key} must be true or false")
    elif key == "concurrent_downloads":
        if type(value) is not int or not 1 <= value <= 16:
            raise click.ClickException("concurrent_downloads must be between 1 and 16")
    elif key == "save_prompt":
        if value not in {"ask", "never"}:
            raise click.ClickException("save_prompt must be ask or never")
    elif key == "default_account":
        if value is not None and not isinstance(value, str):
            raise click.ClickException("default_account must be a username or null")
    elif key == "game_dir_path" and (not isinstance(value, str) or not value):
        raise click.ClickException("game_dir_path must be a nonempty path")
    return value


class Config:
    def __init__(self, path: Path | None = None, *, disabled: bool = False):
        self.path = path or config_path()
        self.disabled = disabled
        self.data = {**DEFAULTS, "accounts": [], "auto_login_accounts": []}
        if disabled:
            return
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as error:
                raise click.ClickException(f"Invalid config file {self.path}: {error}")
            if not isinstance(loaded, dict):
                raise click.ClickException("Config file must contain a JSON object")
            for key, value in loaded.items():
                if key in DEFAULTS:
                    self.data[key] = _validate(key, value)
            # Migrate the old single-account preference in memory. It is
            # persisted on the next configuration change, not on read.
            if "auto_login_accounts" not in loaded:
                default = self.data["default_account"]
                if self.data["auto_login"] and default in self.data["accounts"]:
                    self.data["auto_login_accounts"] = [default]
            self.data["auto_login"] = bool(self.data["auto_login_accounts"])
        else:
            self.save()

    def get(self, key: str) -> Any:
        return self.data[key]

    def set(self, key: str, value: Any) -> None:
        self.update(**{key: value})

    def update(self, **values: Any) -> None:
        if self.disabled:
            raise click.ClickException("Cannot save settings with --no-config-file")
        validated = {key: _validate(key, value) for key, value in values.items()}
        self.data.update(validated)
        self.save()

    def save(self) -> None:
        if self.disabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".config-",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                tmp_name = tmp.name
                if os.name != "nt":
                    os.chmod(tmp_name, 0o600)
                json.dump(self.data, tmp, indent=2)
                tmp.write("\n")
            os.replace(tmp_name, self.path)
        finally:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
