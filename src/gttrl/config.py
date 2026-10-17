"""Non-secret launcher preferences. Keyring secrets never belong in JSON."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import click

from .constants import config_path, game_dir

PASSWORD_POLICIES = frozenset({"ask", "never", "yes"})
ACCOUNT_FIELDS = frozenset({"username", "nickname", "auto_login", "save_password"})
DEFAULTS: dict[str, Any] = {
    "game_dir_path": str(game_dir()),
    "display_game_log": False,
    "skip_update": False,
    "concurrent_downloads": 3,
    "accounts": [],
    "default_account": None,
    # Controls whether *unknown* users are offered registration after login.
    "save_prompt": "ask",
}


def _account(
    username: str,
    *,
    nickname: str | None = None,
    auto_login: bool = False,
    save_password: str = "ask",
) -> dict[str, Any]:
    if not isinstance(username, str) or not username.strip():
        raise click.ClickException("Account username must be a nonempty string")
    if nickname is not None and (not isinstance(nickname, str) or not nickname.strip()):
        raise click.ClickException("Account nickname must be null or nonempty text")
    if not isinstance(auto_login, bool):
        raise click.ClickException("Account auto_login must be a boolean")
    if not isinstance(save_password, str) or save_password not in PASSWORD_POLICIES:
        raise click.ClickException("Account save_password must be ask, never, or yes")
    return {
        "username": username,
        "nickname": nickname,
        "auto_login": auto_login,
        "save_password": save_password,
    }


def _validate(key: str, value: Any) -> Any:
    if key not in DEFAULTS:
        raise click.ClickException(f"Unknown setting: {key}")
    if key == "accounts":
        if not isinstance(value, list):
            raise click.ClickException("accounts must be a list of account objects")
        accounts = []
        for item in value:
            if not isinstance(item, dict) or set(item) != ACCOUNT_FIELDS:
                raise click.ClickException(
                    "Each account must contain username, nickname, auto_login, "
                    "and save_password (no secrets)"
                )
            accounts.append(_account(**item))
        usernames = [item["username"] for item in accounts]
        if len(usernames) != len(set(usernames)):
            raise click.ClickException("Account usernames must be unique")
        labels = [item["nickname"] for item in accounts if item["nickname"]]
        if len(labels) != len(set(labels)) or any(
            item["nickname"] in usernames
            and item["nickname"] != item["username"]
            for item in accounts if item["nickname"]
        ):
            raise click.ClickException("Nicknames must not conflict with other accounts")
        return accounts
    if key in {"display_game_log", "skip_update"}:
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
        self.data = {**DEFAULTS, "accounts": []}
        if disabled:
            return
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as error:
                raise click.ClickException(f"Invalid config file {self.path}: {error}")
            if not isinstance(loaded, dict):
                raise click.ClickException("Config file must contain a JSON object")
            self._load(loaded)
        else:
            self.save()

    def _load(self, loaded: dict[str, Any]) -> None:
        for key, value in loaded.items():
            if key in DEFAULTS and key != "accounts":
                self.data[key] = _validate(key, value)
        items = loaded.get("accounts", [])
        if not isinstance(items, list):
            raise click.ClickException("accounts must be a list")
        if items and all(isinstance(value, str) for value in items):
            # Legacy 2.0 format: old accounts were *all* held in the OS keyring.
            enabled = loaded.get("auto_login_accounts")
            if enabled is None:
                default = loaded.get("default_account")
                enabled = [default] if loaded.get("auto_login") and default else []
            self.data["accounts"] = _validate(
                "accounts",
                [_account(value, auto_login=value in enabled, save_password="yes") for value in items],
            )
        else:
            self.data["accounts"] = _validate("accounts", items)

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
