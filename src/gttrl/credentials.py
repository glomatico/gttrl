"""Remembered accounts backed by the operating system's secure credential store."""

from __future__ import annotations

import click
import keyring
from keyring import errors

from .config import Config

SERVICE = "gttrl"


class CredentialError(click.ClickException):
    pass


class Accounts:
    def __init__(self, config: Config):
        self.config = config

    @property
    def usernames(self) -> list[str]:
        return list(self.config.get("accounts"))

    @staticmethod
    def _check_backend() -> None:
        try:
            backend = keyring.get_keyring()
            if backend.priority <= 0:
                raise CredentialError("No secure OS keyring is available")
            # Explicitly refuse optional third-party file-backed keyrings.
            # Some keyrings.alt backends report a positive priority while
            # storing secrets in a user-controlled (possibly plaintext) file.
            module = type(backend).__module__
            if module.startswith(("keyrings.alt", "keyring.backends.fail", "keyring.backends.null")):
                raise CredentialError("An insecure or unavailable keyring was selected")
        except (errors.KeyringError, RuntimeError) as error:
            raise CredentialError(f"Secure credential storage unavailable: {error}") from error

    def get(self, username: str) -> str:
        if username not in self.usernames:
            raise CredentialError(f"No saved account named {username!r}")
        self._check_backend()
        try:
            password = keyring.get_password(SERVICE, username)
        except errors.KeyringError as error:
            raise CredentialError(f"Cannot access OS keyring: {error}") from error
        if password is None:
            raise CredentialError(f"Saved credentials for {username!r} are missing from the OS keyring")
        return password

    def add(self, username: str, password: str, *, auto_login: bool = False) -> None:
        if self.config.disabled:
            raise CredentialError("Account saving is disabled by --no-config-file")
        self._check_backend()
        try:
            keyring.set_password(SERVICE, username, password)
        except errors.KeyringError as error:
            raise CredentialError(f"Cannot save to OS keyring: {error}") from error
        users = self.usernames
        if username not in users:
            users.append(username)
            self.config.set("accounts", users)
        if self.config.get("default_account") is None or auto_login:
            self.config.set("default_account", username)
        self.config.set("auto_login", auto_login)

    def remove(self, username: str) -> None:
        if username not in self.usernames:
            raise CredentialError(f"No saved account named {username!r}")
        self._check_backend()
        try:
            keyring.delete_password(SERVICE, username)
        except errors.PasswordDeleteError:
            pass
        except errors.KeyringError as error:
            raise CredentialError(f"Cannot remove secret from OS keyring: {error}") from error
        self.config.set("accounts", [u for u in self.usernames if u != username])
        if self.config.get("default_account") == username:
            remaining = self.usernames
            self.config.set("default_account", remaining[0] if remaining else None)
            self.config.set("auto_login", False)
