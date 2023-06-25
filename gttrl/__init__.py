import argparse
from pathlib import Path

from .gttrl import Gttrl

__version__ = "1.0"


def main():
    parser = argparse.ArgumentParser(
        description="Glomatico's Toontown Rewritten Launcher",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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
        default="./account.txt",
        help="Account file location",
    )
    parser.add_argument(
        "-f",
        "--game-path",
        default="./Toontown Rewritten",
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
        help="Enable log",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args()
    username = args.username
    password = args.password
    account_file = args.account_file
    game_path = args.game_path
    play_cookie = args.play_cookie
    game_server = args.game_server
    skip_update = args.skip_update
    print_play_cookie = args.print_play_cookie
    enable_log = args.enable_log
    if (username and not password) or (password and not username):
        raise Exception("Username and password must be provided together")
    elif (play_cookie and not game_server) or (game_server and not play_cookie):
        raise Exception("Play cookie and game server must be provided together")
    else:
        if Path(account_file).exists() and not username and not play_cookie:
            with open(account_file, "r") as file:
                username, password = file.read().splitlines()
        elif not username and not play_cookie:
            raise Exception(
                "Account file does not exist and no others forms of authentication were provided"
            )
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
