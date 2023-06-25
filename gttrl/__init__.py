import argparse
import getpass
from pathlib import Path

from .gttrl import Config, Gttrl

__version__ = "1.1"


def main():
    parser = argparse.ArgumentParser(
        description="Glomatico's Toontown Rewritten Launcher",
    )
    parser.add_argument(
        "-u",
        "--username",
        help="Account username",
    )
    parser.add_argument(
        "-p",
        "--password",
        help="Account password",
    )
    parser.add_argument(
        "-a",
        "--account-file",
        help="Account file location",
    )
    parser.add_argument(
        "-m",
        "--game-path",
        help="Game path",
    )
    parser.add_argument(
        "-c",
        "--play-cookie",
        help="Play cookie",
    )
    parser.add_argument(
        "-g",
        "--game-server",
        help="Game server",
    )
    parser.add_argument(
        "-s",
        "--skip-update",
        action="store_true",
        help="Skip game update",
    )
    parser.add_argument(
        "-k",
        "--print-play-cookie",
        action="store_true",
        help="Print play cookie and game server and exit",
    )
    parser.add_argument(
        "-e",
        "--enable-log",
        action="store_true",
        help="Enable logging to the console",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args()
    config = Config()
    config.create_if_not_exists()
    config_file = config.read_config_file()
    username = args.username
    password = args.password
    account_file = args.account_file or config_file["account_file"]
    game_path = args.game_path or config_file["game_path"]
    play_cookie = args.play_cookie
    game_server = args.game_server
    skip_update = args.skip_update or config_file["skip_update"]
    print_play_cookie = args.print_play_cookie
    enable_log = args.enable_log or config_file["enable_log"]
    if (username and not password) or (password and not username):
        raise Exception("Username and password must be provided together")
    elif (play_cookie and not game_server) or (game_server and not play_cookie):
        raise Exception("Play cookie and game server must be provided together")
    else:
        if Path(account_file).exists() and not username and not play_cookie:
            with open(account_file, "r") as file:
                username, password = file.read().splitlines()
        elif not username and not play_cookie:
            username = input("Username: ")
            password = getpass.getpass("Password: ")
    gttrl = Gttrl(username, password, game_path, enable_log)
    if username:
        print("Logging in...")
        play_cookie, game_server = gttrl.get_play_cookie()
    else:
        pass
    if print_play_cookie:
        print(play_cookie, game_server)
        return
    if not skip_update:
        print("Downloading game files...")
        gttrl.download_game_files()
    print("Launching game...")
    gttrl.launch_game(play_cookie, game_server)
