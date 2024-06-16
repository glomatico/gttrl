from __future__ import annotations

import bz2
import hashlib
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import click
import tqdm
from requests import Session

from .models import LoginResponse


class Launcher:
    LOGIN_API_URL = "https://www.toontownrewritten.com/api/login"
    GAME_FILES_API_URL = "https://download.toontownrewritten.com/patches"
    PATCH_MANIFEST_API_URL = (
        "https://cdn.toontownrewritten.com/content/patchmanifest.txt"
    )

    def __init__(
        self,
        game_dir_path: Path,
        display_game_log: bool,
    ):
        self.game_dir_path = game_dir_path
        self.display_game_log = display_game_log
        self._setup_game_exe()
        self._setup_session()

    def _setup_game_exe(self):
        self.host_os = sys.platform
        if self.host_os == "win32" and platform.architecture()[0] == "64bit":
            self.game_exe_path = "./TTREngine64.exe"
            self.host_os = "win64"
        elif self.host_os == "win32":
            self.game_exe_path = "./TTREngine.exe"
        elif self.host_os == "darwin":
            self.game_exe_path = "./Toontown Rewritten"
        elif self.host_os in ("linux", "linux2"):
            self.game_exe_path = "./TTREngine"
        else:
            raise Exception("Unsupported OS")

    def _setup_session(self):
        self.session = Session()

    def download_file(self, url: str, output_path: Path):
        response = self.session.get(url, stream=True)
        response.raise_for_status()
        chunk_size = 1024
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tqdm.tqdm(
            total=int(response.headers.get("content-length", 0)),
            unit="B",
            unit_scale=True,
            unit_divisor=chunk_size,
            leave=False,
        ) as bar, output_path.open("wb") as file:
            for chunk in response.iter_content(chunk_size):
                if chunk:
                    file.write(chunk)
                    bar.update(len(chunk))

    def decompress_bz2_file(self, input_path: Path, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(bz2.decompress(input_path.read_bytes()))

    def download_game_file(
        self,
        server_filename: str,
        output_path_bz2: Path,
        output_path: Path,
    ):
        download_url = f"{self.GAME_FILES_API_URL}/{server_filename}"
        self.download_file(download_url, output_path_bz2)
        self.decompress_bz2_file(output_path_bz2, output_path)
        os.remove(output_path_bz2)

    def get_file_sha1(self, file_path: Path) -> str:
        hasher = hashlib.sha1()
        hasher.update(file_path.read_bytes())
        return hasher.hexdigest()

    def download_game_files(self):
        if not self.game_dir_path.exists():
            self.game_dir_path.mkdir(parents=True, exist_ok=True)
        manifest = self.session.get(self.PATCH_MANIFEST_API_URL).json()
        game_file_names = [
            key for key in manifest.keys() if self.host_os in manifest[key]["only"]
        ]
        with tqdm.tqdm(
            total=len(game_file_names),
            leave=False,
        ) as bar:
            for game_file_name in game_file_names:
                bar.set_description(game_file_name)
                server_file_name = manifest[game_file_name]["dl"]
                game_file_path = self.game_dir_path / game_file_name
                server_file_path = self.game_dir_path / server_file_name
                file_sha1 = (
                    self.get_file_sha1(game_file_path)
                    if game_file_path.exists()
                    else None
                )
                if not file_sha1 or file_sha1 != manifest[game_file_name]["hash"]:
                    self.download_game_file(
                        server_file_name,
                        server_file_path,
                        game_file_path,
                    )
                bar.update()

    def get_login_response_username_and_password(
        self,
        username: str,
        password: str,
    ) -> dict:
        response = self.session.post(
            self.LOGIN_API_URL,
            params={
                "format": "json",
            },
            data={
                "username": username,
                "password": password,
            },
        )
        response.raise_for_status()
        response = response.json()
        return response

    def get_login_response_twofactor(
        self,
        app_token: str,
        auth_token: str,
    ) -> dict:
        response = self.session.post(
            self.LOGIN_API_URL,
            params={
                "format": "json",
            },
            data={
                "appToken": app_token,
                "authToken": auth_token,
            },
        )
        response.raise_for_status()
        response = response.json()
        return response

    def get_login_response_queue_token(self, queue_token: str) -> dict:
        response = self.session.post(
            self.LOGIN_API_URL,
            params={
                "format": "json",
                "queueToken": queue_token,
            },
        )
        response.raise_for_status()
        response = response.json()
        return response

    def get_login_response(self, username: str, password: str) -> LoginResponse:
        login_response = self.get_login_response_username_and_password(
            username,
            password,
        )
        if login_response["success"] == "partial":
            twofactor_input = click.prompt(login_response["banner"])
            login_response = self.get_login_response_twofactor(
                twofactor_input,
                login_response["responseToken"],
            )
        while login_response["success"] == "delayed":
            time.sleep(3)
            login_response = self.get_login_response_queue_token(
                login_response["queueToken"]
            )
        if login_response["success"] == "false":
            raise Exception(login_response["banner"])
        return LoginResponse(
            play_cookie=login_response["cookie"],
            game_server=login_response["gameserver"],
        )

    def launch_game(self, play_cookie: str, game_server: str):
        os.environ["TTR_PLAYCOOKIE"] = play_cookie
        os.environ["TTR_GAMESERVER"] = game_server
        os.chdir(self.game_dir_path)
        if self.display_game_log:
            subprocess.call([self.game_exe_path])
        elif self.host_os in ("win32", "win64"):
            subprocess.Popen(
                [self.game_exe_path],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            if not os.access(self.game_exe_path, os.X_OK):
                os.chmod(self.game_exe_path, 0o755)
            subprocess.Popen(
                [self.game_exe_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
