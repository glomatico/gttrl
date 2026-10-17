"""GTTRL command-line interface and interactive account selection."""

from __future__ import annotations

import asyncio
import json
import platform
import sys
from pathlib import Path

import click
import httpx
import questionary

from . import __version__, ui
from .auth import AuthClient
from .config import DEFAULTS, Config
from .credentials import Accounts, CredentialError
from .launcher import Launcher
from .updater import Updater


class DefaultPlayGroup(click.Group):
    """Forward legacy `gttrl [PLAY OPTIONS]` invocations to `gttrl play`."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if not args or args[0] not in {
            "play", "accounts", "config", "--help", "-h", "--version", "-v"
        }:
            args = ["play", *args]
        return super().parse_args(ctx, args)


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _prompt_text(message: str, *, password: bool = False) -> str:
    if not _interactive():
        raise click.ClickException(f"{message} is required in non-interactive mode")
    question = questionary.password(message) if password else questionary.text(message)
    result = question.ask()
    if result is None:
        raise click.Abort()
    return result


def _select(message: str, choices: list[tuple[str, str]]) -> str:
    if not _interactive():
        raise click.ClickException(f"Interactive selection required: {message}")
    result = questionary.select(
        message, choices=[questionary.Choice(title, value=value) for title, value in choices]
    ).ask()
    if result is None:
        raise click.Abort()
    return result


def _ask_save(config: Config, accounts: Accounts, username: str, password: str) -> None:
    if config.disabled or config.get("save_prompt") == "never" or not _interactive():
        return
    if username in accounts.usernames:
        return
    choice = _select(
        "Remember this account?",
        [
            ("Save and enable automatic login", "auto"),
            ("Save, but ask which account to use each time", "save"),
            ("Don't save", "no"),
            ("Never ask to save again", "never"),
        ],
    )
    if choice == "never":
        config.set("save_prompt", "never")
    elif choice in {"auto", "save"}:
        try:
            accounts.add(username, password, auto_login=choice == "auto")
        except CredentialError as error:
            ui.error(f"Couldn't remember account: {error.format_message()}")
        else:
            ui.success("Account securely saved to your OS keyring.")


def _choose_credentials(
    accounts: Accounts,
    config: Config,
    account: str | None,
    username: str | None,
    password: str | None,
    choose_account: bool,
    no_saved_login: bool,
) -> tuple[str, str, bool]:
    if account and (username or password or no_saved_login):
        raise click.UsageError("--account cannot be combined with manual credentials or --no-saved-login")
    if choose_account and (account or username or password or no_saved_login):
        raise click.UsageError("--choose-account cannot be combined with explicit credentials")
    if account:
        return account, accounts.get(account), True
    if username or password or no_saved_login:
        return username or _prompt_text("Username"), password or _prompt_text("Password", password=True), False
    users = [] if config.disabled else accounts.usernames
    default = config.get("default_account")
    if users and config.get("auto_login") and default in users and not choose_account:
        return default, accounts.get(default), True
    if users:
        selection = _select(
            "Choose a Toontown Rewritten account:",
            [(user, user) for user in users] + [("Log in with another account", "__new__")],
        )
        if selection != "__new__":
            return selection, accounts.get(selection), True
    return _prompt_text("Username"), _prompt_text("Password", password=True), False


@click.group(cls=DefaultPlayGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-v", "--version", prog_name="gttrl")
def main() -> None:
    """Launch Toontown Rewritten and manage saved accounts."""


@main.command()
@click.option("-u", "--username", help="Log in using this username.")
@click.option("-p", "--password", help="Password (insecure in shell history; prefer prompting).")
@click.option("--password-stdin", is_flag=True, help="Read the password from standard input.")
@click.option("--account", help="Use a remembered account from the OS keyring.")
@click.option("--choose-account", is_flag=True, help="Show the account picker.")
@click.option("--no-saved-login", is_flag=True, help="Ignore remembered accounts for this launch.")
@click.option("--play-cookie", help="Use an externally supplied play cookie.")
@click.option("--game-server", help="Game server for a supplied play cookie.")
@click.option("--login-mode", type=click.Choice(["credentials", "playcookieandgameserver"]), hidden=True)
@click.option("--print-play-cookie-and-game-server", is_flag=True, help="Print sensitive launch credentials and exit.")
@click.option(
    "--skip-update/--check-update",
    default=None,
    help="Skip patch verification or explicitly check for updates.",
)
@click.option("--config-path", type=click.Path(path_type=Path), default=None)
@click.option("--game-dir-path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--display-game-log/--hide-game-log",
    default=None,
    help="Display or hide the game process output.",
)
@click.option("--concurrent-downloads", type=click.IntRange(1, 16), default=None)
@click.option("-n", "--no-config-file", is_flag=True, help="Ignore config and do not persist settings.")
def play(
    username: str | None,
    password: str | None,
    password_stdin: bool,
    account: str | None,
    choose_account: bool,
    no_saved_login: bool,
    play_cookie: str | None,
    game_server: str | None,
    login_mode: str | None,
    print_play_cookie_and_game_server: bool,
    skip_update: bool | None,
    config_path: Path | None,
    game_dir_path: Path | None,
    display_game_log: bool | None,
    concurrent_downloads: int | None,
    no_config_file: bool,
) -> None:
    """Authenticate, update if necessary, and launch the game."""
    if password_stdin and password:
        raise click.UsageError("--password and --password-stdin cannot be combined")
    if password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
        if not password:
            raise click.UsageError("No password was provided on standard input")
    if login_mode:
        ui.warning("--login-mode is deprecated; authentication is now automatic.")
        if login_mode == "playcookieandgameserver" and not (play_cookie or game_server):
            raise click.UsageError("This mode needs --play-cookie and --game-server")
        if login_mode == "credentials" and (play_cookie or game_server):
            raise click.UsageError("Credential login cannot use play-cookie arguments")
    if bool(play_cookie) != bool(game_server):
        raise click.UsageError("--play-cookie and --game-server must be supplied together")
    session_login = bool(play_cookie)
    if session_login and (username or password or password_stdin or account or choose_account or no_saved_login):
        raise click.UsageError("A play cookie cannot be combined with account login options")
    config = Config(config_path, disabled=no_config_file)
    launcher = Launcher(
        game_dir_path or Path(config.get("game_dir_path")),
        config.get("display_game_log") if display_game_log is None else display_game_log,
    )
    manifest = None
    if not session_login:
        accounts = Accounts(config)
        username, password, was_saved = _choose_credentials(
            accounts, config, account, username, password, choose_account, no_saved_login
        )
        ui.info("Logging in...")
        with AuthClient() as auth:
            response = auth.login(
                username,
                password,
                prompt_token=lambda msg: _prompt_text(msg, password=True),
                display=ui.info,
            )
        ui.success("Login successful.")
        play_cookie, game_server, manifest = (
            response.play_cookie, response.game_server, response.manifest
        )
        if not was_saved:
            _ask_save(config, accounts, username, password)
    if print_play_cookie_and_game_server:
        click.echo(f"Play cookie: {play_cookie}\nGame server: {game_server}")
        return
    if not (config.get("skip_update") if skip_update is None else skip_update):
        ui.info("Checking game files...")
        host_os = (
            "win64" if sys.platform == "win32" and platform.architecture()[0] == "64bit"
            else sys.platform
        )
        updater = Updater(
            launcher.game_dir_path,
            host_os,
            concurrency=concurrent_downloads or config.get("concurrent_downloads"),
        )
        try:
            asyncio.run(updater.update(manifest, show_progress=_interactive()))
        except (OSError, ValueError) as error:
            raise click.ClickException(f"Game update failed: {error}") from error
        except httpx.HTTPError as error:
            raise click.ClickException(f"Game update network error: {error}") from error
    ui.info("Launching Toontown Rewritten...")
    launcher.launch_game(play_cookie, game_server)


@main.group()
@click.option("--config-path", type=click.Path(path_type=Path), default=None)
@click.pass_context
def accounts(ctx: click.Context, config_path: Path | None) -> None:
    """Manage accounts whose secrets are stored in the OS keyring."""
    ctx.obj = Accounts(Config(config_path))


@accounts.command("list")
@click.pass_obj
def accounts_list(saved: Accounts) -> None:
    """List saved usernames without displaying secrets."""
    ui.accounts_list(
        saved.usernames,
        default_account=saved.config.get("default_account"),
        auto_login=saved.config.get("auto_login"),
    )


@accounts.command("add")
@click.option("--username", help="Username to add.")
@click.option("--auto-login/--no-auto-login", default=None, help="Use this account automatically.")
@click.pass_obj
def accounts_add(saved: Accounts, username: str | None, auto_login: bool | None) -> None:
    """Authenticate and securely remember an account."""
    username = username or _prompt_text("Username")
    password = _prompt_text("Password", password=True)
    with AuthClient() as auth:
        auth.login(username, password, prompt_token=lambda msg: _prompt_text(msg, password=True))
    if auto_login is None:
        if not _interactive():
            auto_login = False
        else:
            auto_login = _select("Enable automatic login?", [("Yes", True), ("No, ask each time", False)])
    saved.add(username, password, auto_login=auto_login)
    ui.success(f"Saved {username!r} securely.")


@accounts.command("remove")
@click.argument("username")
@click.pass_obj
def accounts_remove(saved: Accounts, username: str) -> None:
    """Remove one saved account and its secret."""
    saved.remove(username)
    ui.success(f"Removed {username!r}.")


@accounts.command("clear")
@click.confirmation_option(prompt="Remove all saved accounts?")
@click.pass_obj
def accounts_clear(saved: Accounts) -> None:
    """Remove all saved accounts from the OS keyring."""
    for username in saved.usernames:
        saved.remove(username)
    ui.success("All saved accounts removed.")


@accounts.command("default")
@click.argument("username")
@click.pass_obj
def accounts_default(saved: Accounts, username: str) -> None:
    """Choose the default remembered account."""
    if username not in saved.usernames:
        raise click.ClickException(f"Account {username!r} is not saved")
    saved.config.set("default_account", username)
    ui.success(f"Default account: {username}")


@accounts.command("auto-login")
@click.argument("state", type=click.Choice(["on", "off"]))
@click.pass_obj
def accounts_auto_login(saved: Accounts, state: str) -> None:
    """Enable or disable automatic login using the default account."""
    if state == "on" and saved.config.get("default_account") not in saved.usernames:
        raise click.ClickException("Choose a default saved account first")
    saved.config.set("auto_login", state == "on")
    ui.success(f"Auto-login: {state}")


@main.group()
@click.option("--config-path", type=click.Path(path_type=Path), default=None)
@click.pass_context
def config(ctx: click.Context, config_path: Path | None) -> None:
    """Inspect or adjust non-sensitive launcher settings."""
    ctx.obj = Config(config_path)


@config.command("show")
@click.pass_obj
def config_show(settings: Config) -> None:
    click.echo(json.dumps(settings.data, indent=2))


@config.command("get")
@click.argument("key")
@click.pass_obj
def config_get(settings: Config, key: str) -> None:
    key = key.replace("-", "_")
    if key not in DEFAULTS:
        raise click.ClickException(f"Unknown setting: {key}")
    click.echo(json.dumps(settings.get(key)))


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_obj
def config_set(settings: Config, key: str, value: str) -> None:
    key = key.replace("-", "_")
    if key in {"accounts", "default_account", "auto_login"}:
        raise click.ClickException("Manage accounts through gttrl accounts instead")
    try:
        parsed = json.loads(value)
    except ValueError:
        parsed = value
    settings.set(key, parsed)
    ui.success(f"{key} updated.")


@config.command("reset")
@click.confirmation_option(prompt="Reset launcher preferences?")
@click.pass_obj
def config_reset(settings: Config) -> None:
    for key in ("game_dir_path", "display_game_log", "skip_update", "concurrent_downloads", "save_prompt"):
        settings.data[key] = DEFAULTS[key]
    settings.save()
    ui.success("Preferences reset. Saved accounts preserved.")
