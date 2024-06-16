from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

import click

from . import __version__
from .constants import *
from .enums import LoginMode
from .launcher import Launcher
from .models import LoginResponse


def get_param_string(param: click.Parameter) -> str:
    if isinstance(param.default, Enum):
        return param.default.value
    elif isinstance(param.default, Path):
        return str(param.default)
    else:
        return param.default


def write_default_config_file(ctx: click.Context):
    ctx.params["config_path"].parent.mkdir(parents=True, exist_ok=True)
    config_file = {
        param.name: get_param_string(param)
        for param in ctx.command.params
        if param.name not in EXCLUDED_CONFIG_FILE_PARAMS
    }
    ctx.params["config_path"].write_text(json.dumps(config_file, indent=4))


def load_config_file(
    ctx: click.Context,
    param: click.Parameter,
    no_config_file: bool,
) -> click.Context:
    if no_config_file:
        return ctx
    if not ctx.params["config_path"].exists():
        write_default_config_file(ctx)
    config_file = dict(json.loads(ctx.params["config_path"].read_text()))
    for param in ctx.command.params:
        if (
            config_file.get(param.name) is not None
            and not ctx.get_parameter_source(param.name)
            == click.core.ParameterSource.COMMANDLINE
        ):
            ctx.params[param.name] = param.type_cast_value(ctx, config_file[param.name])
    return ctx


@click.command()
@click.help_option("-h", "--help")
@click.version_option(
    __version__,
    "-v",
    "--version",
    prog_name=__package__,
)
# CLI specific options
@click.option(
    "-u",
    "--username",
    help="Username.",
    type=str,
)
@click.option(
    "-p",
    "--password",
    help="Password.",
    type=str,
)
@click.option(
    "--play-cookie",
    help="Play cookie.",
    type=str,
)
@click.option(
    "--game-server",
    help="Game server.",
    type=str,
)
@click.option(
    "--login-mode",
    help="Login mode.",
    type=LoginMode,
    default=LoginMode.CREDENTIALS,
)
@click.option(
    "--print-play-cookie-and-game-server",
    help="Print play cookie and game server and exit.",
    is_flag=True,
)
@click.option(
    "--skip-update",
    help="Skip checking for game updates.",
    is_flag=True,
)
@click.option(
    "--config-path",
    help="Path to the config file.",
    type=Path,
    default=DEFAULT_CONFIG_FILE_PATH,
)
# Launcher specific options
@click.option(
    "--game-dir-path",
    help="Path to the game directory.",
    type=Path,
    default=DEFAULT_GAME_DIR_PATH,
)
@click.option(
    "--display-game-log",
    help="Display game log on terminal.",
    is_flag=True,
)
# This option should always be last
@click.option(
    "--no-config-file",
    "-n",
    is_flag=True,
    callback=load_config_file,
    help="Don't load the config file.",
)
def main(
    username: str,
    password: str,
    play_cookie: str,
    game_server: str,
    login_mode: LoginMode,
    print_play_cookie_and_game_server: bool,
    skip_update: bool,
    config_path: Path,
    game_dir_path: Path,
    display_game_log: bool,
    no_config_file: bool,
):
    launcher = Launcher(
        game_dir_path=game_dir_path,
        display_game_log=display_game_log,
    )
    if login_mode == LoginMode.CREDENTIALS:
        username = username or click.prompt("Username")
        password = password or click.prompt("Password", hide_input=True)
        click.echo("Logging in")
        login_response = launcher.get_login_response(username, password)
    elif login_mode == LoginMode.PLAY_COOKIE_AND_GAME_SERVER:
        login_response = LoginResponse(
            play_cookie=play_cookie or click.prompt("Play cookie"),
            game_server=game_server or click.prompt("Game server"),
        )
    if print_play_cookie_and_game_server:
        click.echo(f"Play Cookie: {login_response.play_cookie}")
        click.echo(f"Game server: {login_response.game_server}")
        return
    if not skip_update:
        click.echo("Downloading/updating game files")
        launcher.download_game_files()
    click.echo("Launching game")
    launcher.launch_game(
        play_cookie=login_response.play_cookie,
        game_server=login_response.game_server,
    )
