import configparser
import json
import time
from pathlib import Path

import click

from . import __version__
from .constants import *
from .launcher import Launcher


def write_default_config_file(ctx: click.Context) -> None:
    ctx.params["config_file_path"].parent.mkdir(parents=True, exist_ok=True)
    config_file = {
        param.name: (
            param.default if param.name not in STR_CAST_PARAMS else str(param.default)
        )
        for param in ctx.command.params
        if param.name not in EXCLUDED_CONFIG_FILE_PARAMS
    }
    with open(ctx.params["config_file_path"], "w") as f:
        f.write(json.dumps(config_file, indent=4))


def no_config_callback(
    ctx: click.Context, param: click.Parameter, no_config_file: bool
) -> click.Context:
    if not no_config_file:
        if not ctx.params["config_file_path"].exists():
            write_default_config_file(ctx)
        with open(ctx.params["config_file_path"], "r") as f:
            config_file = dict(json.load(f))
        for param in ctx.command.params:
            if (
                config_file.get(param.name) is not None
                and not ctx.get_parameter_source(param.name)
                == click.core.ParameterSource.COMMANDLINE
            ):
                ctx.params[param.name] = param.type_cast_value(
                    ctx, config_file[param.name]
                )
    return ctx


def create_default_accounts_file(accounts_file_path: Path) -> None:
    accounts_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(accounts_file_path, "w") as f:
        f.write(DEFAULT_ACCOUNTS_FILE_CONTENT)


def get_accounts_file(accounts_file_path: Path) -> dict:
    config_parser = configparser.ConfigParser()
    config_parser.read_file(accounts_file_path.open())
    return dict(config_parser.items())


@click.command()
@click.option(
    "-l",
    "--login-mode",
    type=click.Choice(["credentials", "accountsfile", "playcookieandserver"]),
    default="credentials",
    help="Login mode to use.",
)
@click.option(
    "--username",
    "-u",
    type=str,
    help="Account username.",
)
@click.option(
    "--password",
    "-p",
    type=str,
    help="Account password.",
)
@click.option(
    "--account-name",
    "-a",
    type=str,
    help="Account name provided in accounts file.",
)
@click.option(
    "--accounts-file-path",
    type=Path,
    help="Path to a .ini file containing account credentials",
    default=DEFAULT_ACCOUNTS_FILE_PATH,
)
@click.option(
    "--play-cookie",
    type=str,
    help="Play cookie.",
)
@click.option(
    "--game-server",
    type=str,
    help="Game server.",
)
@click.option(
    "--config-file-path",
    "-c",
    type=Path,
    help="Path to a .json file containing the launcher configuration.",
    default=DEFAULT_CONFIG_FILE_PATH,
)
@click.option(
    "--game-dir-path",
    "-g",
    type=Path,
    help="Path to Toontown Rewritten game directory.",
    default=DEFAULT_GAME_DIR_PATH,
)
@click.option(
    "--no-config-file",
    "-n",
    is_flag=True,
    help="Don't read from config file and don't write the default config file.",
    callback=no_config_callback,
)
@click.option(
    "--display-game-log",
    "-d",
    is_flag=True,
    help="Display the game log in the terminal.",
)
@click.option(
    "-s",
    "--skip-update",
    is_flag=True,
    help="Skip checking for game updates.",
)
@click.option(
    "--print-play-cookie-and-server",
    is_flag=True,
    help="Print the play cookie and game server and exit.",
)
@click.help_option("-h", "--help")
@click.version_option(__version__, "-v", "--version")
def main(
    login_mode: str,
    username: str,
    password: str,
    account_name: str,
    accounts_file_path: Path,
    play_cookie: str,
    game_server: str,
    config_file_path: Path,
    game_dir_path: Path,
    no_config_file: bool,
    display_game_log: bool,
    skip_update: bool,
    print_play_cookie_and_server: bool,
):
    launcher = Launcher(**locals())
    launcher.setup_game_exe()
    if launcher.game_exe is None:
        click.echo("Unsupported OS")
        return
    launcher.setup_session()
    if login_mode in ("credentials", "accountsfile"):
        if login_mode == "credentials":
            username = username or click.prompt("Username")
            password = password or click.prompt("Password", hide_input=True)
        else:
            if not accounts_file_path.exists():
                click.echo("Creating default accounts file")
                create_default_accounts_file(accounts_file_path)
                click.echo(
                    "The default accounts file has been created, "
                    "re-run the launcher again after adding your account(s) to the file"
                )
                return
            account_name = account_name or click.prompt("Account name")
            accounts_file = get_accounts_file(accounts_file_path)
            if not accounts_file.get(account_name):
                click.echo(
                    "The account name provided doesn't exist in the accounts file"
                )
                return
            username = accounts_file[account_name]["username"]
            password = accounts_file[account_name]["password"]
        click.echo("Logging in")
        login_response = launcher.get_login_response_username_and_password(
            username, password
        )
        if login_response["success"] == "false":
            click.echo(login_response["banner"])
            return
        while login_response["success"] == "partial":
            toonguard_input = click.prompt(login_response["banner"])
            login_response = launcher.get_login_response_toonguard(
                toonguard_input,
                login_response["responseToken"],
            )
        while login_response["success"] == "delayed":
            login_response = launcher.get_login_response_queue_token(
                queue_token=login_response["queueToken"]
            )
            time.sleep(3)
        play_cookie, game_server = (
            login_response["cookie"],
            login_response["gameserver"],
        )
    elif login_mode == "playcookieandserver":
        play_cookie = play_cookie or click.prompt("Play cookie")
        game_server = game_server or click.prompt("Game server")
    if print_play_cookie_and_server:
        click.echo(f"Play cookie: {play_cookie}")
        click.echo(f"Game server: {game_server}")
        return
    if not skip_update:
        click.echo("Downloading/updating game files")
        launcher.download_game_files()
    click.echo("Launching game")
    launcher.launch_game(play_cookie, game_server)
