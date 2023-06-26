import argparse
import getpass
from pathlib import Path

from .gttrl import Config, Gttrl

__version__ = "1.2"


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
    username, password = None, None
    if Path(config_file["account_file"]).exists():
        with open(config_file["account_file"]) as f:
            username, password = f.read().splitlines()
    elif args.account_file:
        with open(args.account_file, "w") as f:
            f.write(f"{username}\n{password}")
    elif not args.play_cookie and not args.game_server:
        username = args.username or input("Username: ")
        password = args.password or getpass.getpass("Password: ")
    else:
        play_cookie = args.play_cookie or input("Play cookie: ")
        game_server = args.game_server or input("Game server: ")
    gttrl = Gttrl(
        username,
        password,
        args.game_path or config_file["game_path"],
        args.enable_log or config_file["enable_log"],
    )
    if username:
        print("Logging in...")
        play_cookie, game_server = gttrl.get_play_cookie()
        if args.print_play_cookie:
            print(f"{play_cookie}\n{game_server}")
            return
    else:
        pass
    if not (args.skip_update or config_file["skip_update"]):
        print("Downloading game files...")
        gttrl.download_game_files()
    print("Launching game...")
    gttrl.launch_game(play_cookie, game_server)
