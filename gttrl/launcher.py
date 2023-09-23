import bz2
import hashlib
import os
import platform
import subprocess
import sys
from pathlib import Path

import tqdm
from requests import Session

from .constants import API_URL_GAME_FILES, API_URL_LOGIN, API_URL_PATCH_MANIFEST


class Launcher:
    def __init__(
        self,
        game_dir_path: Path,
        display_game_log: bool,
        **kwargs,
    ):
        self.game_dir_path = game_dir_path
        self.display_game_log = display_game_log

    def setup_game_exe(self) -> None:
        self.os = sys.platform
        if self.os == "win32" and platform.architecture()[0] == "64bit":
            self.game_exe = "./TTREngine64.exe"
            self.os = "win64"
        elif self.os == "win32":
            self.game_exe = "./TTREngine.exe"
        elif self.os == "darwin":
            self.game_exe = "./Toontown Rewritten"
        elif self.os == "linux" or self.os == "linux2":
            self.game_exe = "./TTREngine"
        else:
            self.game_exe = None

    def setup_session(self) -> None:
        self.session = Session()

    def download_game_file(self, filename_server: str, game_file_path: Path) -> None:
        game_file_response = self.session.get(
            f"{API_URL_GAME_FILES}/{filename_server}",
            stream=True,
        )
        chunk_size = 1024
        game_file_temp_path = game_file_path.parent / filename_server
        with open(game_file_temp_path, "wb") as file, tqdm.tqdm(
            total=int(game_file_response.headers.get("content-length", 0)),
            unit="B",
            unit_scale=True,
            unit_divisor=chunk_size,
            leave=False,
        ) as bar:
            for chunk in game_file_response.iter_content(chunk_size):
                if chunk:
                    file.write(chunk)
                    bar.update(len(chunk))
        with open(game_file_temp_path, "rb") as file:
            game_file_temp_content = file.read()
        with open(game_file_path, "wb") as file:
            file.write(bz2.decompress(game_file_temp_content))
        os.remove(game_file_temp_path)

    def get_file_sha1(self, file_location: Path) -> str:
        hasher = hashlib.sha1()
        with open(file_location, "rb") as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    def download_game_files(self) -> None:
        if not self.game_dir_path.exists():
            self.game_dir_path.mkdir(parents=True, exist_ok=True)
        manifest = self.session.get(API_URL_PATCH_MANIFEST).json()
        keys = list(manifest.keys())
        for key in keys:
            if self.os not in manifest[key]["only"]:
                del manifest[key]
        progress_bar = tqdm.tqdm(
            manifest.keys(),
            leave=False,
        )
        for file in manifest.keys():
            progress_bar.set_description(file)
            filename_server = manifest[file]["dl"]
            game_file_path = self.game_dir_path / file
            if not game_file_path.exists():
                self.download_game_file(filename_server, game_file_path)
            else:
                file_sha1 = self.get_file_sha1(game_file_path)
                if file_sha1 != manifest[file]["hash"]:
                    self.download_game_file(filename_server, game_file_path)
            progress_bar.update()
        progress_bar.close()

    def get_login_response_username_and_password(
        self,
        username: str,
        password: str,
    ) -> dict:
        login_response = self.session.post(
            API_URL_LOGIN,
            params={
                "format": "json",
            },
            data={
                "username": username,
                "password": password,
            },
        )
        login_response.raise_for_status()
        login_response = login_response.json()
        return login_response

    def get_login_response_toonguard(
        self, toonguard_input: str, toonguard_token: str
    ) -> dict:
        login_response = self.session.post(
            API_URL_LOGIN,
            params={
                "format": "json",
                "appToken": toonguard_token,
                "authToken": toonguard_input,
            },
        )
        login_response.raise_for_status()
        login_response = login_response.json()
        return login_response

    def get_login_response_queue_token(self, queue_token: str) -> dict:
        login_response = self.session.post(
            API_URL_LOGIN,
            params={
                "format": "json",
                "queueToken": queue_token,
            },
        )
        login_response.raise_for_status()
        login_response = login_response.json()
        return login_response

    def launch_game(self, play_cookie: str, game_server: str) -> None:
        os.environ["TTR_PLAYCOOKIE"] = play_cookie
        os.environ["TTR_GAMESERVER"] = game_server
        os.chdir(self.game_dir_path)
        if self.display_game_log:
            subprocess.call([self.game_exe])
        elif self.os == "win32" or self.os == "win64":
            subprocess.Popen(
                [self.game_exe],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            if not os.access(self.game_exe, os.X_OK):
                os.chmod(self.game_exe, 0o755)
            subprocess.Popen(
                [self.game_exe],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
