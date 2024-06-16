from pathlib import Path

EXCLUDED_CONFIG_FILE_PARAMS = (
    "username",
    "password",
    "play_cookie",
    "game_server",
    "config_path",
    "no_config_file",
    "version",
    "help",
)

DEFAULT_LAUNCHER_DIR_PATH = Path.home() / ".gttrl"

DEFAULT_GAME_DIR_PATH = DEFAULT_LAUNCHER_DIR_PATH / "game"

DEFAULT_CONFIG_FILE_PATH = DEFAULT_LAUNCHER_DIR_PATH / "config.json"
