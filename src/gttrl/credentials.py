"""Account preferences and optional OS-keyring password persistence."""

from __future__ import annotations

import click
import keyring
from keyring import errors

from .config import Config, _account

SERVICE = "gttrl"


class CredentialError(click.ClickException):
    pass


class Accounts:
    def __init__(self, config: Config):
        self.config = config

    @property
    def records(self) -> list[dict]:
        return [dict(record) for record in self.config.get("accounts")]

    @property
    def usernames(self) -> list[str]:
        return [record["username"] for record in self.records]

    @property
    def auto_launch_accounts(self) -> list[str]:
        return [record["username"] for record in self.records if record["auto_launch"]]

    def resolve(self, identifier: str) -> str:
        for record in self.records:
            if identifier in {record["username"], record["alias"]}:
                return record["username"]
        raise CredentialError(f"No saved account named {identifier!r}")

    def account(self, identifier: str) -> dict:
        username = self.resolve(identifier)
        return next(item for item in self.records if item["username"] == username)

    def label(self, identifier: str) -> str:
        record = self.account(identifier)
        alias = record["alias"]
        return f"{alias} ({record['username']})" if alias else record["username"]

    def set_auto_launch(self, usernames: list[str]) -> None:
        selected = [self.resolve(username) for username in usernames]
        if len(selected) != len(set(selected)):
            raise CredentialError("Automatic launch accounts must be unique")
        records = self.records
        for record in records:
            record["auto_launch"] = record["username"] in selected
        self.config.set("accounts", records)

    @staticmethod
    def _check_backend() -> None:
        try:
            backend = keyring.get_keyring()
            if backend.priority <= 0:
                raise CredentialError("No secure OS keyring is available")
            module = type(backend).__module__
            if module.startswith(("keyrings.alt", "keyring.backends.fail", "keyring.backends.null")):
                raise CredentialError("An insecure or unavailable keyring was selected")
        except (errors.KeyringError, RuntimeError) as error:
            raise CredentialError(f"Secure credential storage unavailable: {error}") from error

    def get(self, identifier: str) -> str:
        username = self.resolve(identifier)
        if not self.account(username)["save_password"]:
            raise CredentialError(f"Account {username!r} is not set to use a saved password")
        return self.keyring_password(username)

    def keyring_password(self, username: str) -> str:
        self._check_backend()
        try:
            password = keyring.get_password(SERVICE, username)
        except errors.KeyringError as error:
            raise CredentialError(f"Cannot access OS keyring: {error}") from error
        if password is None:
            raise CredentialError(f"No password for {username!r} in the OS keyring")
        return password

    def _store_password(self, username: str, password: str) -> None:
        self._check_backend()
        try:
            keyring.set_password(SERVICE, username, password)
        except errors.KeyringError as error:
            raise CredentialError(f"Cannot save to OS keyring: {error}") from error

    def _delete_password(self, username: str) -> None:
        self._check_backend()
        try:
            keyring.delete_password(SERVICE, username)
        except errors.PasswordDeleteError:
            pass
        except errors.KeyringError as error:
            raise CredentialError(f"Cannot remove secret from OS keyring: {error}") from error

    def add(
        self,
        username: str,
        password: str,
        *,
        auto_launch: bool | None = None,
        exclusive_auto_launch: bool = False,
        alias: str | None = None,
        save_password: bool = True,
    ) -> None:
        if self.config.disabled:
            raise CredentialError("Account saving is disabled by --no-config-file")
        if exclusive_auto_launch and not auto_launch:
            raise CredentialError("Exclusive auto-launch requires auto_launch=True")
        if not isinstance(save_password, bool):
            raise CredentialError("save_password must be true or false")
        records = self.records
        previous = next((item for item in records if item["username"] == username), None)
        record = _account(
            username,
            alias=alias if alias is not None else (
                previous["alias"] if previous else None
            ),
            auto_launch=(
                bool(previous and previous["auto_launch"])
                if auto_launch is None else auto_launch
            ),
            save_password=save_password,
        )
        if exclusive_auto_launch:
            for item in records:
                item["auto_launch"] = False
            record["auto_launch"] = True
        if previous is not None:
            records = [record if item["username"] == username else item for item in records]
        else:
            records.append(record)

        # Validate account data before touching the keyring.
        from .config import _validate
        _validate("accounts", records)
        if save_password:
            self._store_password(username, password)
        elif previous and previous["save_password"]:
            self._delete_password(username)
        self.config.set("accounts", records)

    def update_password(self, identifier: str, password: str) -> None:
        username = self.resolve(identifier)
        if not self.account(username)["save_password"]:
            raise CredentialError("Enable saved passwords for this account first")
        self._store_password(username, password)

    def set_alias(self, identifier: str, alias: str | None) -> None:
        username = self.resolve(identifier)
        records = self.records
        for item in records:
            if item["username"] == username:
                item["alias"] = alias
        self.config.set("accounts", records)

    def set_password_saving(
        self, identifier: str, enabled: bool, *, password: str | None = None
    ) -> None:
        username = self.resolve(identifier)
        if not isinstance(enabled, bool):
            raise CredentialError("Password saving must be true or false")
        if enabled:
            if password is not None:
                self._store_password(username, password)
            else:
                self.keyring_password(username)
        else:
            # Remove any old credential even for migrated ask/never policies.
            self._delete_password(username)
        records = self.records
        for item in records:
            if item["username"] == username:
                item["save_password"] = enabled
        self.config.set("accounts", records)

    def remove(self, identifier: str) -> None:
        username = self.resolve(identifier)
        if self.account(username)["save_password"]:
            self._delete_password(username)
        remaining = [item for item in self.records if item["username"] != username]
        self.config.set("accounts", remaining)
