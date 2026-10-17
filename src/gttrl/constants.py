import os
from pathlib import Path


def launcher_dir() -> Path:
    return Path.home() / ".gttrl"


def config_path() -> Path:
    return Path(os.environ.get("GTTRL_CONFIG_PATH", launcher_dir() / "config.json"))


def game_dir() -> Path:
    return launcher_dir() / "game"


DEFAULT_PATCH_MANIFEST = "https://cdn.toontownrewritten.com/content/patchmanifest.txt"
