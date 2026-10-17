"""GTTRL command-line interface and interactive account selection."""

from __future__ import annotations

import asyncio
import json
import platform
import sys
import time
from pathlib import Path

import click
import httpx
import questionary

from . import __version__, ui
from .auth import AuthClient, LoginRejected
from .config import DEFAULTS, PASSWORD_POLICIES, Config
from .credentials import Accounts, CredentialError
from .launcher import Launcher
from .models import LoginResponse
from .updater import Updater


class DefaultPlayGroup(click.Group):
    """Forward legacy `gttrl [PLAY OPTIONS]` invocations to `gttrl play`."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if not args or args[0] not in {
            "play", "accounts", "config", "--help", "-h", "--version", "-v"
        }:
            args = ["play", *args]
        return super().parse_args(ctx, args)


class LoginModeChoice(click.Choice):
    """Keep the v1 spelling valid without cluttering the new help output."""

    def __init__(self):
        super().__init__(["auto", "credentials", "play-cookie"], case_sensitive=False)

    def convert(self, value, param, ctx):
        if isinstance(value, str) and value.casefold() == "playcookieandgameserver":
            return "playcookieandgameserver"
        return super().convert(value, param, ctx)


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


def _select_auto_accounts(saved: Accounts) -> list[str]:
    if not saved.usernames:
        raise click.ClickException("Add a saved account before configuring automatic login")
    if not _interactive():
        raise click.ClickException(
            "Interactive selection requires a terminal; use 'gttrl accounts auto-login set USERNAME ...'"
        )
    selected = set(saved.auto_login_accounts)
    result = questionary.checkbox(
        "Select accounts to launch automatically (space to toggle):",
        choices=[
            questionary.Choice(saved.label(username), value=username, checked=username in selected)
            for username in saved.usernames
        ],
    ).ask()
    if result is None:
        raise click.Abort()
    return result


def _session_value(value: str | None, label: str, *, secret: bool = False) -> str:
    """Use a supplied session value or ask for the missing one."""
    value = value or _prompt_text(label, password=secret)
    if not value.strip():
        raise click.UsageError(f"{label} cannot be empty")
    return value


def _new_account_choices() -> list[tuple[str, str]]:
    """Actions for storing another account when one is already remembered."""
    return [
        ("Exclusive auto-login (replace selected accounts)", "exclusive"),
        ("Add to auto-login (launch alongside existing accounts)", "add"),
        ("Just add (do not change auto-login)", "save"),
    ]


def _save_account(
    accounts: Accounts, username: str, password: str, choice: str,
    *, save_password: str = "yes", nickname: str | None = None,
) -> None:
    accounts.add(
        username,
        password,
        auto_login=choice in {"auto", "exclusive", "add"},
        exclusive_auto_login=choice == "exclusive",
        save_password=save_password,
        nickname=nickname,
    )


def _password_policy_choice(message: str = "Remember the password?") -> str:
    return _select(message, [
        ("Yes — use the OS keyring next time", "yes"),
        ("Ask — let me choose how to log in each time", "ask"),
        ("Never — always prompt for a password", "never"),
    ])


def _ask_save(config: Config, accounts: Accounts, username: str, password: str) -> None:
    if config.disabled or config.get("save_prompt") == "never" or not _interactive():
        return
    if username in accounts.usernames:
        return
    save_options = (
        _new_account_choices()
        if accounts.usernames
        else [
            ("Save and enable automatic login", "auto"),
            ("Save, but ask which account to use each time", "save"),
        ]
    )
    choice = _select(
        "Remember this account?",
        save_options + [
            ("Don't save", "no"),
            ("Never ask to save again", "never"),
        ],
    )
    if choice == "never":
        config.set("save_prompt", "never")
    elif choice in {"auto", "save", "exclusive", "add"}:
        try:
            policy = _password_policy_choice()
            _save_account(accounts, username, password, choice, save_password=policy)
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
) -> tuple[str, str | None, bool]:
    if account and (username or password or no_saved_login):
        raise click.UsageError("--account cannot be combined with manual credentials or --no-saved-login")
    if choose_account and (account or username or password or no_saved_login):
        raise click.UsageError("--choose-account cannot be combined with explicit credentials")
    if account:
        return accounts.resolve(account), None, True
    if username or password or no_saved_login:
        return username or _prompt_text("Username"), password or _prompt_text("Password", password=True), False
    users = [] if config.disabled else accounts.usernames
    if users:
        selection = _select(
            "Choose a Toontown Rewritten account:",
            [(accounts.label(user), user) for user in users]
            + [("Log in with another account", "__new__")],
        )
        if selection != "__new__":
            return selection, None, True
    return _prompt_text("Username"), _prompt_text("Password", password=True), False


def _selected_credentials(
    accounts: Accounts,
    config: Config,
    account: str | None,
    username: str | None,
    password: str | None,
    choose_account: bool,
    no_saved_login: bool,
) -> list[tuple[str, str | None, bool]]:
    explicit = bool(account or username is not None or password is not None or
                    choose_account or no_saved_login)
    if not explicit and not config.disabled and accounts.auto_login_accounts:
        return [
            (user, None, True)
            for user in accounts.auto_login_accounts
        ]
    return [
        _choose_credentials(
            accounts, config, account, username, password,
            choose_account, no_saved_login,
        )
    ]


def _authenticate(
    auth: AuthClient,
    accounts: Accounts,
    config: Config,
    username: str,
    password: str | None,
    was_saved: bool,
):
    """Respect account password policy and recover rejected keyring credentials."""
    policy = accounts.account(username)["save_password"] if was_saved else None
    prompted_for_password = False
    if password is None and was_saved:
        if policy == "never":
            password = _prompt_text(f"Password for {accounts.label(username)}", password=True)
        elif policy == "ask":
            choice = _select(
                f"How should GTTRL log in as {accounts.label(username)}?",
                [
                    ("Use a password from the OS keyring", "keyring"),
                    ("Enter the password", "manual"),
                    ("Skip this account", "skip"),
                ],
            )
            if choice == "skip":
                return None
            if choice == "manual":
                password = _prompt_text("Password", password=True)
                prompted_for_password = True
        if password is None:
            try:
                password = accounts.keyring_password(username)
            except CredentialError as error:
                if not _interactive():
                    raise
                ui.warning(f"Couldn't retrieve password for {username}: {error.format_message()}")
                password = _prompt_text("Password", password=True)
                prompted_for_password = True
    if password is None:
        password = _prompt_text("Password", password=True)

    while True:
        ui.info(f"Logging in as {username}...")
        try:
            response = auth.login(
                username,
                password,
                prompt_token=lambda msg: _prompt_text(msg, password=True),
                display=ui.info,
            )
        except LoginRejected as error:
            if not was_saved or not _interactive():
                raise
            ui.warning(f"Login for {username} was rejected: {error.format_message()}")
            action = _select(
                "What would you like to do?",
                [
                    ("Re-enter password", "retry"),
                    ("Skip this account", "skip"),
                    ("Cancel launch", "cancel"),
                ],
            )
            if action == "skip":
                return None
            if action == "cancel":
                raise click.Abort() from error
            password = _prompt_text("New password", password=True)
            prompted_for_password = True
        else:
            ui.success(f"Successfully authenticated as {username}.")
            if was_saved and prompted_for_password and policy in {"yes", "ask"} and _interactive():
                choice = _password_policy_choice(
                    "How should GTTRL handle this account's password in the future?"
                )
                try:
                    accounts.set_password_policy(
                        username, choice,
                        password=password if choice == "yes" else None,
                    )
                except CredentialError as error:
                    ui.error(f"Couldn't update the password preference: {error.format_message()}")
                else:
                    ui.success("Password preference updated.")
            if not was_saved:
                _ask_save(config, accounts, username, password)
            return response


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
@click.option(
    "--login-mode",
    type=LoginModeChoice(),
    default="auto",
    show_default=True,
    help="Authentication method. 'auto' infers it from supplied options; "
    "'playcookieandgameserver' is a legacy alias for 'play-cookie'.",
)
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
    if login_mode == "playcookieandgameserver":
        ui.warning("Use --login-mode play-cookie instead of the legacy mode name.")
    session_login = (
        login_mode in {"play-cookie", "playcookieandgameserver"}
        or (
            login_mode == "auto"
            and (play_cookie is not None or game_server is not None)
        )
    )
    if session_login:
        if any((
            username is not None, password is not None, password_stdin,
            account is not None, choose_account, no_saved_login,
        )):
            raise click.UsageError("Play-cookie login cannot be combined with account login options")
        play_cookie = _session_value(play_cookie, "Play cookie", secret=True)
        game_server = _session_value(game_server, "Game server")
    else:
        if play_cookie is not None or game_server is not None:
            raise click.UsageError(
                "Credential login cannot use --play-cookie or --game-server"
            )
        if password_stdin and password is not None:
            raise click.UsageError("--password and --password-stdin cannot be combined")
        if password_stdin:
            password = sys.stdin.readline().rstrip("\r\n")
            if not password:
                raise click.UsageError("No password was provided on standard input")
    config = Config(config_path, disabled=no_config_file)
    launcher = Launcher(
        game_dir_path or Path(config.get("game_dir_path")),
        config.get("display_game_log") if display_game_log is None else display_game_log,
    )
    manifest = None
    sessions = []
    if not session_login:
        accounts = Accounts(config)
        selections = _selected_credentials(
            accounts, config, account, username, password, choose_account, no_saved_login
        )
        if print_play_cookie_and_game_server and len(selections) > 1:
            raise click.UsageError(
                "Cannot print multiple session credentials. Use --account USERNAME to select one."
            )
        if len(selections) > 1:
            ui.info(f"Multi-login: authenticating {len(selections)} accounts.")
        with AuthClient() as auth:
            for selected_user, selected_password, was_saved in selections:
                response = _authenticate(
                    auth, accounts, config, selected_user, selected_password, was_saved
                )
                if response is not None:
                    sessions.append((selected_user, response))
        if not sessions:
            raise click.ClickException("No accounts were authenticated; nothing to launch")
    if print_play_cookie_and_game_server:
        if not session_login:
            play_cookie = sessions[0][1].play_cookie
            game_server = sessions[0][1].game_server
        click.echo(f"Play cookie: {play_cookie}\nGame server: {game_server}")
        return
    if session_login:
        sessions = [("Session", LoginResponse(play_cookie, game_server))]
    manifests = {response.manifest for _, response in sessions}
    if len(manifests) > 1:
        raise click.ClickException(
            "Accounts received different patch manifests; refusing to share one game installation"
        )
    manifest = sessions[0][1].manifest
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
    processes = []
    for selected_user, response in sessions:
        ui.info(f"Launching Toontown Rewritten for {selected_user}...")
        processes.append((selected_user, launcher.launch_game(
            response.play_cookie, response.game_server
        )))
    if launcher.display_game_log:
        failures = []
        for selected_user, process in processes:
            if process is not None and process.wait() != 0:
                failures.append(selected_user)
        if failures:
            raise click.ClickException(
                f"Game exited unsuccessfully for: {', '.join(failures)}"
            )
    else:
        # Check for immediate startup failures once after launching all
        # sessions. Running game clients remain detached.
        time.sleep(0.25)
        failed = [
            f"{selected_user} (exit {process.poll()})"
            for selected_user, process in processes
            if process is not None and process.poll() is not None
        ]
        if failed:
            raise click.ClickException(
                "Game closed immediately for "
                + ", ".join(failed)
                + ". Try --display-game-log for diagnostics."
            )


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
        auto_login=bool(saved.auto_login_accounts),
        auto_login_accounts=saved.auto_login_accounts,
        nicknames={
            item["username"]: item["nickname"] for item in saved.records
        },
        password_policies={
            item["username"]: item["save_password"] for item in saved.records
        },
    )


@accounts.command("add")
@click.option("--username", help="Username to add.")
@click.option("--nickname", help="Optional friendly label for the account.")
@click.option(
    "--save-password",
    type=click.Choice(sorted(PASSWORD_POLICIES)),
    default=None,
    help="Password policy: yes (keyring), ask (choose each time), never (prompt).",
)
@click.option("--auto-login/--no-auto-login", default=None, help="Use this account automatically.")
@click.option(
    "--exclusive-auto-login",
    is_flag=True,
    help="Use only this account for automatic login, replacing previous selections.",
)
@click.pass_obj
def accounts_add(
    saved: Accounts,
    username: str | None,
    nickname: str | None,
    save_password: str | None,
    auto_login: bool | None,
    exclusive_auto_login: bool,
) -> None:
    """Authenticate and securely remember an account."""
    if exclusive_auto_login and auto_login is not None:
        raise click.UsageError(
            "--exclusive-auto-login cannot be combined with --auto-login or --no-auto-login"
        )
    username = username or _prompt_text("Username")
    had_other_accounts = any(user != username for user in saved.usernames)
    password = _prompt_text("Password", password=True)
    with AuthClient() as auth:
        auth.login(username, password, prompt_token=lambda msg: _prompt_text(msg, password=True))
    if exclusive_auto_login:
        choice = "exclusive"
    elif auto_login is not None:
        choice = "add" if auto_login else "save"
    elif not _interactive():
        choice = "save"
    elif had_other_accounts:
        choice = _select("How should this account be saved?", _new_account_choices())
    else:
        choice = _select(
            "Enable automatic login?",
            [("Yes", "auto"), ("No, ask each time", "save")],
        )
    policy = save_password or (
        _password_policy_choice() if _interactive() else "yes"
    )
    _save_account(
        saved, username, password, choice,
        nickname=nickname, save_password=policy,
    )
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
    canonical = saved.resolve(username)
    saved.config.set("default_account", canonical)
    ui.success(f"Default account: {saved.label(canonical)}")


@accounts.command("nickname")
@click.argument("username")
@click.argument("nickname", required=False)
@click.option("--clear", is_flag=True, help="Remove the nickname.")
@click.pass_obj
def accounts_nickname(
    saved: Accounts, username: str, nickname: str | None, clear: bool
) -> None:
    """Give a saved account a friendly name; use --clear to remove it."""
    if clear == (nickname is not None):
        raise click.UsageError("Provide a nickname or use --clear")
    canonical = saved.resolve(username)
    saved.set_nickname(canonical, None if clear else nickname)
    ui.success(f"Account label: {saved.label(canonical)}")


@accounts.command("save-password")
@click.argument("username")
@click.argument("policy", type=click.Choice(sorted(PASSWORD_POLICIES)))
@click.pass_obj
def accounts_save_password(saved: Accounts, username: str, policy: str) -> None:
    """Control use of OS-keyring passwords for a saved account."""
    canonical = saved.resolve(username)
    if policy == "yes":
        try:
            saved.set_password_policy(canonical, "yes")
        except CredentialError:
            # A password can be stored only after the user authenticates.
            password = _prompt_text("Password", password=True)
            with AuthClient() as auth:
                auth.login(
                    canonical, password,
                    prompt_token=lambda msg: _prompt_text(msg, password=True),
                )
            saved.set_password_policy(canonical, "yes", password=password)
    else:
        saved.set_password_policy(canonical, policy)
    ui.success(f"Password preference for {saved.label(canonical)}: {policy}.")


@accounts.command("auto-login")
@click.argument("action", required=False, type=click.Choice(
    ["on", "off", "set", "list"], case_sensitive=False
))
@click.argument("usernames", nargs=-1)
@click.pass_obj
def accounts_auto_login(saved: Accounts, action: str | None, usernames: tuple[str, ...]) -> None:
    """Select multiple accounts for automatic login and game launching.

    Run without arguments for an interactive checkbox selector.
    Or use: auto-login set USER1 USER2 ...
    """
    if action != "set" and usernames:
        raise click.UsageError("Account names can only follow 'auto-login set'")
    if action == "list":
        if saved.auto_login_accounts:
            for username in saved.auto_login_accounts:
                click.echo(username)
        else:
            click.echo("No accounts selected for automatic login.")
        return
    if action == "set":
        if not usernames:
            raise click.UsageError("Specify at least one saved account or use 'auto-login off'")
        selected = list(usernames)
    elif action == "on":
        selected = saved.auto_login_accounts
        if not selected:
            default = saved.config.get("default_account")
            if default not in saved.usernames:
                raise click.ClickException("Choose a default saved account first")
            selected = [default]
    elif action == "off":
        selected = []
    else:
        selected = _select_auto_accounts(saved)
    saved.set_auto_login(selected)
    ui.success(
        f"Automatic login configured for {len(selected)} account(s)."
    )


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
    if key in {"accounts", "default_account", "auto_login", "auto_login_accounts"}:
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
