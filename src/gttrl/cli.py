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
from .config import DEFAULTS, Config
from .credentials import Accounts, CredentialError
from .launcher import Launcher
from .models import LoginResponse
from .updater import Updater


class DefaultPlayGroup(click.Group):
    """Allow launching with `gttrl` as well as `gttrl play`."""

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


def _yes_no(message: str) -> bool:
    return _select(message, [("Yes", "yes"), ("No", "no")]) == "yes"


def _select_auto_accounts(saved: Accounts) -> list[str]:
    if not saved.usernames:
        raise click.ClickException("Add a saved account before configuring auto-launch")
    if not _interactive():
        raise click.ClickException(
            "Interactive selection requires a terminal; use 'gttrl accounts auto-launch set USERNAME ...'"
        )
    selected = set(saved.auto_launch_accounts)
    result = questionary.checkbox(
        "Select accounts to auto-launch (space to toggle):",
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


def _save_account(
    accounts: Accounts, username: str, password: str, *,
    auto_launch: bool = False, save_password: bool = False,
    alias: str | None = None,
) -> None:
    accounts.add(
        username,
        password,
        auto_launch=auto_launch,
        save_password=save_password,
        alias=alias,
    )


def _ask_save(config: Config, accounts: Accounts, username: str, password: str) -> None:
    if config.disabled or not config.get("account_wizard") or not _interactive():
        return
    if username in accounts.usernames:
        return
    if not _yes_no("Remember this account?"):
        return
    alias = _prompt_optional_alias()
    auto_launch = _yes_no("Enable auto-launch?")
    save_password = _yes_no("Remember the password?")
    try:
        _save_account(
            accounts, username, password,
            auto_launch=auto_launch, save_password=save_password, alias=alias,
        )
    except CredentialError as error:
        ui.error(f"Couldn't remember account: {error.format_message()}")
    else:
        ui.success("Account remembered." + (
            " Password saved to the OS keyring." if save_password else ""
        ))


def _prompt_optional_alias() -> str | None:
    alias = _prompt_text("Account alias (optional, no spaces)")
    return alias or None


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
    chosen_accounts: tuple[str, ...] = (),
) -> list[tuple[str, str | None, bool]]:
    if chosen_accounts:
        if account or username is not None or password is not None or choose_account or no_saved_login:
            raise click.UsageError(
                "--accounts cannot be combined with --account, manual credentials, or --choose-account"
            )
        resolved = [accounts.resolve(name) for name in chosen_accounts]
        if len(resolved) != len(set(resolved)):
            raise click.UsageError("--accounts contains the same account more than once")
        return [(name, None, True) for name in resolved]
    explicit = bool(account or username is not None or password is not None or
                    choose_account or no_saved_login)
    if not explicit and not config.disabled and accounts.auto_launch_accounts:
        return [
            (user, None, True)
            for user in accounts.auto_launch_accounts
        ]
    if not config.get("account_wizard") and not accounts.usernames and not explicit:
        raise click.UsageError(
            "Account wizard is disabled: provide --username and --password "
            "(or --password-stdin)"
        )
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
    *,
    allow_account_wizard: bool = True,
    quiet: bool = False,
):
    """Use remembered passwords when enabled; repair missing/rejected secrets."""
    remember_password = accounts.account(username)["save_password"] if was_saved else False
    should_store = False
    if password is None and was_saved:
        if not remember_password:
            password = _prompt_text(f"Password for {accounts.label(username)}", password=True)
        else:
            try:
                password = accounts.keyring_password(username)
            except CredentialError as error:
                if not _interactive():
                    raise
                ui.warning(f"Couldn't retrieve password for {username}: {error.format_message()}")
                password = _prompt_text("Password", password=True)
                should_store = True
    if password is None:
        password = _prompt_text("Password", password=True)

    while True:
        if not quiet:
            ui.info(f"Logging in as {username}...")
        try:
            response = auth.login(
                username,
                password,
                prompt_token=lambda msg: _prompt_text(msg, password=True),
                display=(lambda _message: None) if quiet else ui.info,
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
            should_store = remember_password
        else:
            if not quiet:
                ui.success(f"Successfully authenticated as {username}.")
            if was_saved and should_store:
                try:
                    accounts.update_password(username, password)
                except CredentialError as error:
                    ui.warning(f"Couldn't save the recovered password: {error.format_message()}")
                else:
                    ui.success("Recovered password saved to the OS keyring.")
            if (
                not quiet and not was_saved and allow_account_wizard
                and config.get("account_wizard")
            ):
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
@click.option("--account", help="Use a single saved account by username or alias.")
@click.option(
    "--accounts", "selected_accounts", multiple=True, metavar="NAME",
    help="Launch listed saved accounts (aliases or usernames); commas or spaces accepted.",
)
@click.argument("additional_accounts", nargs=-1)
@click.option("--choose-account", is_flag=True, help="Show the account picker.")
@click.option("--no-saved-login", is_flag=True, help="Ignore remembered accounts for this launch.")
@click.option("--play-cookie", help="Use an externally supplied play cookie.")
@click.option("--game-server", help="Game server for a supplied play cookie.")
@click.option(
    "--ask-play-cookie/--no-ask-play-cookie",
    default=None,
    help="Prompt for a play cookie and game server, or override this saved preference.",
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
@click.option(
    "--account-wizard/--no-account-wizard", default=None,
    help="Override the saved account setup wizard preference for this launch.",
)
@click.option("-n", "--no-config-file", is_flag=True, help="Ignore config and do not persist settings.")
def play(
    username: str | None,
    password: str | None,
    password_stdin: bool,
    account: str | None,
    selected_accounts: tuple[str, ...],
    additional_accounts: tuple[str, ...],
    choose_account: bool,
    no_saved_login: bool,
    play_cookie: str | None,
    game_server: str | None,
    ask_play_cookie: bool | None,
    print_play_cookie_and_game_server: bool,
    skip_update: bool | None,
    config_path: Path | None,
    game_dir_path: Path | None,
    display_game_log: bool | None,
    concurrent_downloads: int | None,
    account_wizard: bool | None,
    no_config_file: bool,
) -> None:
    """Authenticate, update if necessary, and launch the game."""
    if additional_accounts and not selected_accounts:
        raise click.UsageError("Account names must follow --accounts")
    chosen = tuple(
        name.strip() for item in (*selected_accounts, *additional_accounts)
        for name in item.split(",")
    )
    if any(not name for name in chosen):
        raise click.UsageError("--accounts cannot contain an empty account name")
    config = Config(config_path, disabled=no_config_file)
    if account_wizard is not None:
        config.account_wizard_override = account_wizard
    explicit_credentials = any((
        username is not None, password is not None, password_stdin,
        account is not None, choose_account, no_saved_login, bool(chosen),
    ))
    cookie_options = play_cookie is not None or game_server is not None
    if (cookie_options or ask_play_cookie is True) and explicit_credentials:
        raise click.UsageError(
            "Play-cookie login cannot be combined with account login options"
        )
    session_login = (
        cookie_options
        or ask_play_cookie is True
        or (ask_play_cookie is None and not explicit_credentials
            and config.get("ask_play_cookie"))
    )
    if session_login:
        play_cookie = _session_value(play_cookie, "Play cookie", secret=True)
        game_server = _session_value(game_server, "Game server")
    else:
        if password_stdin and password is not None:
            raise click.UsageError("--password and --password-stdin cannot be combined")
        if password_stdin:
            password = sys.stdin.readline().rstrip("\r\n")
            if not password:
                raise click.UsageError("No password was provided on standard input")
    if not print_play_cookie_and_game_server:
        ui.banner(__version__)
    launcher = Launcher(
        game_dir_path or Path(config.get("game_dir_path")),
        config.get("display_game_log") if display_game_log is None else display_game_log,
    )
    manifest = None
    sessions = []
    if not session_login:
        accounts = Accounts(config)
        selections = _selected_credentials(
            accounts, config, account, username, password, choose_account,
            no_saved_login, chosen,
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
                    auth, accounts, config, selected_user, selected_password, was_saved,
                    allow_account_wizard=username is None,
                    quiet=print_play_cookie_and_game_server,
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


@main.group(invoke_without_command=True)
@click.option("--config-path", type=click.Path(path_type=Path), default=None)
@click.pass_context
def accounts(ctx: click.Context, config_path: Path | None) -> None:
    """Manage saved accounts (interactive menu with no subcommand)."""
    ctx.obj = Accounts(Config(config_path))
    if ctx.invoked_subcommand is None or ctx.invoked_subcommand == "add":
        ui.banner(__version__)
    if ctx.invoked_subcommand is None:
        _account_manager(ctx.obj)


def _enable_password_saving(saved: Accounts, username: str) -> None:
    """Verify credentials before enabling/overwriting a keyring secret."""
    warning = (
        f"Enabling password saving for {saved.label(username)} will save/overwrite "
        "its password in your operating system keyring."
    )
    ui.warning(warning)
    if _select("Proceed?", [("Yes, enter a new password", "yes"), ("Back", "no")]) != "yes":
        return
    password = _prompt_text("New password", password=True)
    with AuthClient() as auth:
        auth.login(
            username, password,
            prompt_token=lambda msg: _prompt_text(msg, password=True),
            display=ui.info,
        )
    saved.set_password_saving(username, True, password=password)
    ui.success("Verified password saved to the OS keyring.")


def _account_manager(saved: Accounts) -> None:
    """Guided editor, independent of the automatic setup wizard setting."""
    while True:
        choices = [(saved.label(name), name) for name in saved.usernames]
        choices.extend([("+ Add account", "__add__"), ("Exit", "__exit__")])
        selected = _select("Select an account to manage:", choices)
        if selected == "__exit__":
            return
        if selected == "__add__":
            # Use the explicit command's existing authentication and add flow.
            click.get_current_context().invoke(accounts_add)
            continue
        username = saved.resolve(selected)
        while username in saved.usernames:
            record = saved.account(username)
            option = _select(
                f"Manage {saved.label(username)}:",
                [
                    (f"Edit password saving ({'enabled' if record['save_password'] else 'disabled'})", "policy"),
                    ("Edit alias", "alias"),
                    (f"Edit auto-launch ({'enabled' if record['auto_launch'] else 'disabled'})", "auto"),
                    ("Launch this account", "play"),
                    ("Remove this account", "remove"),
                    ("Back to accounts", "back"),
                ],
            )
            if option == "back":
                break
            if option == "policy":
                action = _select(
                    "Password saving:",
                    [
                        ("Enable (save/overwrite password in OS keyring)", "enable"),
                        ("Disable (remove keyring password, ask at login)", "disable"),
                        ("Back", "back"),
                    ],
                )
                if action == "enable":
                    _enable_password_saving(saved, username)
                elif action == "disable":
                    saved.set_password_saving(username, False)
                    ui.success("Password saving disabled; keyring secret removed.")
            elif option == "alias":
                alias = _prompt_optional_alias()
                saved.set_alias(username, alias)
                ui.success(f"Account alias: {saved.label(username)}")
            elif option == "auto":
                action = _select(
                    "Auto-launch:", [("Enable", "enable"), ("Disable", "disable"), ("Back", "back")]
                )
                if action == "back":
                    continue
                selected_accounts = saved.auto_launch_accounts
                if action == "enable" and username not in selected_accounts:
                    selected_accounts.append(username)
                if action == "disable" and username in selected_accounts:
                    selected_accounts.remove(username)
                saved.set_auto_launch(selected_accounts)
                ui.success("Auto-launch selection updated.")
            elif option == "play":
                click.get_current_context().parent.invoke(
                    play, account=username, config_path=saved.config.path
                )
                return
            elif option == "remove" and _select(
                "Remove account and any saved keyring password?",
                [("Remove", "yes"), ("Cancel", "no")],
            ) == "yes":
                saved.remove(username)
                ui.success(f"Removed {username}.")
                break


@accounts.command("list")
@click.pass_obj
def accounts_list(saved: Accounts) -> None:
    """List saved usernames without displaying secrets."""
    ui.accounts_list(
        saved.usernames,
        auto_launch_accounts=saved.auto_launch_accounts,
        aliases={
            item["username"]: item["alias"] for item in saved.records
        },
        password_policies={
            item["username"]: item["save_password"] for item in saved.records
        },
    )


@accounts.command("add")
@click.option("--username", help="Username to add.")
@click.option("--alias", help="Optional unique account alias (no spaces).")
@click.option("--save-password/--no-save-password", default=None, help="Save the password in the OS keyring.")
@click.option("--auto-launch/--no-auto-launch", default=None, help="Launch this account automatically.")
@click.option(
    "--exclusive-auto-launch",
    is_flag=True,
    help="Auto-launch only this account, replacing previous selections.",
)
@click.pass_obj
def accounts_add(
    saved: Accounts,
    username: str | None,
    alias: str | None,
    save_password: bool | None,
    auto_launch: bool | None,
    exclusive_auto_launch: bool,
) -> None:
    """Authenticate and securely remember an account."""
    if exclusive_auto_launch and auto_launch is not None:
        raise click.UsageError(
            "--exclusive-auto-launch cannot be combined with --auto-launch or --no-auto-launch"
        )
    username = username or _prompt_text("Username")
    password = _prompt_text("Password", password=True)
    with AuthClient() as auth:
        auth.login(username, password, prompt_token=lambda msg: _prompt_text(msg, password=True))
    if _interactive() and not _yes_no("Remember this account?"):
        ui.info("Account used for authentication but not remembered.")
        return
    if alias is None and _interactive():
        alias = _prompt_optional_alias()
    if auto_launch is None:
        auto_launch = _yes_no("Enable auto-launch?") if _interactive() else False
    if save_password is None:
        save_password = _yes_no("Remember the password?") if _interactive() else True
    _save_account(
        saved, username, password,
        auto_launch=auto_launch or exclusive_auto_launch,
        alias=alias, save_password=save_password,
    )
    if exclusive_auto_launch:
        saved.set_auto_launch([username])
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


@accounts.command("alias")
@click.argument("username")
@click.argument("alias", required=False)
@click.option("--clear", is_flag=True, help="Remove the alias.")
@click.pass_obj
def accounts_alias(
    saved: Accounts, username: str, alias: str | None, clear: bool
) -> None:
    """Give an account a CLI-friendly alias; use --clear to remove it."""
    if clear == (alias is not None):
        raise click.UsageError("Provide an alias or use --clear")
    canonical = saved.resolve(username)
    saved.set_alias(canonical, None if clear else alias)
    ui.success(f"Account label: {saved.label(canonical)}")


@accounts.command("save-password")
@click.argument("username")
@click.argument("policy", type=click.Choice(["enable", "disable"]))
@click.pass_obj
def accounts_save_password(saved: Accounts, username: str, policy: str) -> None:
    """Control use of OS-keyring passwords for a saved account."""
    canonical = saved.resolve(username)
    if policy == "enable":
        _enable_password_saving(saved, canonical)
    else:
        saved.set_password_saving(canonical, False)
        ui.success(f"Password saving disabled for {saved.label(canonical)}.")


@accounts.command("auto-launch")
@click.argument("action", required=False, type=click.Choice(
    ["on", "off", "set", "list"], case_sensitive=False
))
@click.argument("usernames", nargs=-1)
@click.pass_obj
def accounts_auto_launch(saved: Accounts, action: str | None, usernames: tuple[str, ...]) -> None:
    """Select saved accounts for automatic launching.

    Run without arguments for an interactive checkbox selector.
    Or use: auto-launch set USER1 USER2 ...
    """
    if action != "set" and usernames:
        raise click.UsageError("Account names can only follow 'auto-launch set'")
    if action == "list":
        if saved.auto_launch_accounts:
            for username in saved.auto_launch_accounts:
                click.echo(username)
        else:
            click.echo("No accounts selected for auto-launch.")
        return
    if action == "set":
        if not usernames:
            raise click.UsageError("Specify an account or use 'auto-launch off'")
        selected = list(usernames)
    elif action == "on":
        selected = saved.auto_launch_accounts
        if not selected:
            if not saved.usernames:
                raise click.ClickException("Save an account first")
            selected = [saved.usernames[0]]
    elif action == "off":
        selected = []
    else:
        selected = _select_auto_accounts(saved)
    saved.set_auto_launch(selected)
    ui.success(
        f"Auto-launch configured for {len(selected)} account(s)."
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
    if key == "accounts":
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
    for key in (
        "game_dir_path", "display_game_log", "skip_update",
        "concurrent_downloads", "account_wizard", "ask_play_cookie",
    ):
        settings.data[key] = DEFAULTS[key]
    settings.save()
    ui.success("Preferences reset. Saved accounts preserved.")
