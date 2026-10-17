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

    @property
    def auto_login_accounts(self) -> list[str]:
        return list(self.config.get("auto_login_accounts"))

    def set_auto_login(self, usernames: list[str]) -> None:
        unknown = [username for username in usernames if username not in self.usernames]
        if unknown:
            raise CredentialError(f"Unknown saved account(s): {', '.join(unknown)}")
        if len(usernames) != len(set(usernames)):
            raise CredentialError("Automatic login accounts must be unique")
        self.config.update(
            auto_login_accounts=usernames,
            auto_login=bool(usernames),
        )

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

    def add(
        self,
        username: str,
        password: str,
        *,
        auto_login: bool = False,
        exclusive_auto_login: bool = False,
    ) -> None:
        """Store credentials without disturbing existing auto-login selections.

        auto_login adds this account to the selected set; exclusive_auto_login
        replaces that set with only this account.
        """
        if self.config.disabled:
            raise CredentialError("Account saving is disabled by --no-config-file")
        if exclusive_auto_login and not auto_login:
            raise CredentialError("Exclusive auto-login requires auto_login=True")
        self._check_backend()
        try:
            keyring.set_password(SERVICE, username, password)
        except errors.KeyringError as error:
            raise CredentialError(f"Cannot save to OS keyring: {error}") from error
        users = self.usernames
        if username not in users:
            users.append(username)
        selected = [] if exclusive_auto_login else self.auto_login_accounts
        if auto_login and username not in selected:
            selected.append(username)
        self.config.update(
            accounts=users,
            default_account=(
                username if exclusive_auto_login
                else self.config.get("default_account") or username
            ),
            auto_login_accounts=selected,
            auto_login=bool(selected),
        )

    def update_password(self, username: str, password: str) -> None:
        """Replace the saved secret without changing any account preferences."""
        if username not in self.usernames:
            raise CredentialError(f"No saved account named {username!r}")
        self._check_backend()
        try:
            keyring.set_password(SERVICE, username, password)
        except errors.KeyringError as error:
            raise CredentialError(f"Cannot update OS keyring: {error}") from error

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
        remaining = [u for u in self.usernames if u != username]
        selected = [u for u in self.auto_login_accounts if u != username]
        default = self.config.get("default_account")
        if default == username:
            default = remaining[0] if remaining else None
        self.config.update(
            accounts=remaining,
            default_account=default,
            auto_login_accounts=selected,
            auto_login=bool(selected),
        )
