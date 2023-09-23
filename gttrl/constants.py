from pathlib import Path

EXCLUDED_CONFIG_FILE_PARAMS = (
    "username",
    "password",
    "play_cookie",
    "game_server",
    "config_file_path",
    "no_config_file",
    "version",
    "help",
)

STR_CAST_PARAMS = (
    "accounts_file_path",
    "game_dir_path",
)

API_URL_LOGIN = "https://www.toontownrewritten.com/api/login"

API_URL_GAME_FILES = "https://download.toontownrewritten.com/patches"

API_URL_PATCH_MANIFEST = "https://cdn.toontownrewritten.com/content/patchmanifest.txt"

DEFAULT_GTTRL_DIR_PATH = Path.home() / ".gttrl"

DEFAULT_GAME_DIR_PATH = DEFAULT_GTTRL_DIR_PATH / "Toontown Rewritten"

DEFAULT_CONFIG_FILE_PATH = DEFAULT_GTTRL_DIR_PATH / "config.json"

DEFAULT_ACCOUNTS_FILE_PATH = DEFAULT_GTTRL_DIR_PATH / "accounts.ini"

DEFAULT_ACCOUNTS_FILE_CONTENT = (
    "[myaccount]\nusername=myusername\npassword=mypassword\n"
)
