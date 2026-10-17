"""Account preferences and optional OS-keyring password persistence."""

from __future__ import annotations

import click
import keyring
from keyring import errors

from .config import PASSWORD_POLICIES, Config, _account

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
    def auto_login_accounts(self) -> list[str]:
        return [record["username"] for record in self.records if record["auto_login"]]

    def resolve(self, identifier: str) -> str:
        for record in self.records:
            if identifier in {record["username"], record["nickname"]}:
                return record["username"]
        raise CredentialError(f"No saved account named {identifier!r}")

    def account(self, identifier: str) -> dict:
        username = self.resolve(identifier)
        return next(item for item in self.records if item["username"] == username)

    def label(self, identifier: str) -> str:
        record = self.account(identifier)
        nickname = record["nickname"]
        return f"{nickname} ({record['username']})" if nickname else record["username"]

    def set_auto_login(self, usernames: list[str]) -> None:
        selected = [self.resolve(username) for username in usernames]
        if len(selected) != len(set(selected)):
            raise CredentialError("Automatic login accounts must be unique")
        records = self.records
        for record in records:
            record["auto_login"] = record["username"] in selected
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
        if self.account(username)["save_password"] != "yes":
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
        auto_login: bool = False,
        exclusive_auto_login: bool = False,
        nickname: str | None = None,
        save_password: str = "yes",
    ) -> None:
        if self.config.disabled:
            raise CredentialError("Account saving is disabled by --no-config-file")
        if exclusive_auto_login and not auto_login:
            raise CredentialError("Exclusive auto-login requires auto_login=True")
        if save_password not in PASSWORD_POLICIES:
            raise CredentialError("save_password must be ask, never, or yes")
        records = self.records
        previous = next((item for item in records if item["username"] == username), None)
        record = _account(
            username,
            nickname=nickname if nickname is not None else (
                previous["nickname"] if previous else None
            ),
            auto_login=auto_login or bool(previous and previous["auto_login"]),
            save_password=save_password,
        )
        if exclusive_auto_login:
            for item in records:
                item["auto_login"] = False
            record["auto_login"] = True
        if previous is not None:
            records = [record if item["username"] == username else item for item in records]
        else:
            records.append(record)

        # Validate account data before touching the keyring.
        from .config import _validate
        _validate("accounts", records)
        if save_password == "yes":
            self._store_password(username, password)
        elif save_password == "never" and previous and previous["save_password"] != "never":
            self._delete_password(username)
        self.config.update(
            accounts=records,
            default_account=(
                username if exclusive_auto_login
                else self.config.get("default_account") or username
            ),
        )

    def update_password(self, identifier: str, password: str) -> None:
        username = self.resolve(identifier)
        if self.account(username)["save_password"] != "yes":
            raise CredentialError("Enable saved passwords for this account first")
        self._store_password(username, password)

    def set_nickname(self, identifier: str, nickname: str | None) -> None:
        username = self.resolve(identifier)
        records = self.records
        for item in records:
            if item["username"] == username:
                item["nickname"] = nickname
        self.config.set("accounts", records)

    def set_password_policy(
        self, identifier: str, policy: str, *, password: str | None = None
    ) -> None:
        username = self.resolve(identifier)
        if policy not in PASSWORD_POLICIES:
            raise CredentialError("Password policy must be ask, never, or yes")
        if policy == "yes":
            if password is not None:
                self._store_password(username, password)
            else:
                self.keyring_password(username)
        elif policy == "never" and self.account(username)["save_password"] != "never":
            self._delete_password(username)
        records = self.records
        for item in records:
            if item["username"] == username:
                item["save_password"] = policy
        self.config.set("accounts", records)

    def remove(self, identifier: str) -> None:
        username = self.resolve(identifier)
        if self.account(username)["save_password"] != "never":
            self._delete_password(username)
        remaining = [item for item in self.records if item["username"] != username]
        default = self.config.get("default_account")
        if default == username:
            default = remaining[0]["username"] if remaining else None
        self.config.update(accounts=remaining, default_account=default)
