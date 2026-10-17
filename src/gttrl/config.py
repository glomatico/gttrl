"""Non-secret launcher preferences. Keyring secrets never belong in JSON."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import click

from .constants import config_path, game_dir

ACCOUNT_FIELDS = frozenset({"username", "alias", "auto_launch", "save_password"})
DEFAULTS: dict[str, Any] = {
    "game_dir_path": str(game_dir()),
    "display_game_log": False,
    "skip_update": False,
    "concurrent_downloads": 3,
    "accounts": [],
    "account_wizard": True,
}


def _account(
    username: str,
    *,
    alias: str | None = None,
    auto_launch: bool = False,
    save_password: bool = False,
) -> dict[str, Any]:
    if not isinstance(username, str) or not username.strip():
        raise click.ClickException("Account username must be a nonempty string")
    if alias is not None and (
        not isinstance(alias, str) or not alias or any(char.isspace() for char in alias)
        or alias.startswith("-") or "," in alias
    ):
        raise click.ClickException(
            "Account alias must contain no spaces, commas or leading dashes"
        )
    if not isinstance(auto_launch, bool):
        raise click.ClickException("Account auto_launch must be a boolean")
    if not isinstance(save_password, bool):
        raise click.ClickException("Account save_password must be a boolean")
    return {
        "username": username,
        "alias": alias,
        "auto_launch": auto_launch,
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
                    "Each account must contain username, alias, auto_launch, "
                    "and save_password (no secrets)"
                )
            accounts.append(_account(**item))
        usernames = [item["username"] for item in accounts]
        if len(usernames) != len(set(usernames)):
            raise click.ClickException("Account usernames must be unique")
        labels = [item["alias"] for item in accounts if item["alias"]]
        if len(labels) != len(set(labels)) or any(
            item["alias"] in usernames
            and item["alias"] != item["username"]
            for item in accounts if item["alias"]
        ):
            raise click.ClickException("Aliases must not conflict with other accounts")
        return accounts
    if key in {"display_game_log", "skip_update", "account_wizard"}:
        if not isinstance(value, bool):
            raise click.ClickException(f"{key} must be true or false")
    elif key == "concurrent_downloads":
        if type(value) is not int or not 1 <= value <= 16:
            raise click.ClickException("concurrent_downloads must be between 1 and 16")
    elif key == "game_dir_path" and (not isinstance(value, str) or not value):
        raise click.ClickException("game_dir_path must be a nonempty path")
    return value


class Config:
    def __init__(self, path: Path | None = None, *, disabled: bool = False):
        self.path = path or config_path()
        self.disabled = disabled
        self.account_wizard_override: bool | None = None
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
        # Migrate the pre-wizard global opt-out without re-prompting users who
        # previously selected "Never ask again".
        if "account_wizard" not in loaded and loaded.get("save_prompt") == "never":
            self.data["account_wizard"] = False
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
                [_account(value, auto_launch=value in enabled, save_password=True) for value in items],
            )
        else:
            converted = []
            for item in items:
                if isinstance(item, dict) and "nickname" in item and "alias" not in item:
                    old_nickname = item["nickname"]
                    if isinstance(old_nickname, str):
                        # Pre-release nicknames could contain spaces; retain
                        # their meaning while migrating to CLI-friendly aliases.
                        candidate = re.sub(r"[\s,]+", "_", old_nickname.strip()).lstrip("-")
                        old_nickname = candidate or None
                    item = {
                        ("alias" if key == "nickname" else key): (
                            old_nickname if key == "nickname" else value
                        )
                        for key, value in item.items()
                    }
                if isinstance(item, dict):
                    item = dict(item)
                    if "auto_login" in item and "auto_launch" not in item:
                        item["auto_launch"] = item.pop("auto_login")
                    # Pre-release policies were ask, never or yes. Only yes
                    # requested automatic retrieval from the OS keyring.
                    policy = item.get("save_password")
                    if isinstance(policy, str) and policy in {"ask", "never", "yes"}:
                        item["save_password"] = policy == "yes"
                converted.append(item)
            self.data["accounts"] = _validate("accounts", converted)

    def get(self, key: str) -> Any:
        if key == "account_wizard" and self.account_wizard_override is not None:
            return self.account_wizard_override
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
