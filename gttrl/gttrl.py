import bz2
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from requests import Session
from tqdm import tqdm


class Gttrl:
    def __init__(
        self,
        username: str = "",
        password: str = "",
        game_path: str = "./Toontown Rewritten",
        enable_log: bool = False,
    ):
        self.username = username
        self.password = password
        self.game_path = Path(game_path)
        self.enable_log = enable_log
        self.session = Session()
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
            raise Exception("Unsupported OS")

    def download_game_file(self, file_server: str, file_location: Path):
        response = self.session.get(
            f"https://download.toontownrewritten.com/patches/{file_server}",
            stream=True,
        )
        total_size_in_bytes = int(response.headers.get("content-length", 0))
        block_size = 1024
        progress_bar = tqdm(
            total=total_size_in_bytes,
            leave=False,
            unit="iB",
            unit_scale=True,
        )
        file_server_location = file_location.parent / file_server
        with open(file_server_location, "wb") as file:
            for data in response.iter_content(block_size):
                progress_bar.update(len(data))
                file.write(data)
        progress_bar.close()
        with open(file_server_location, "rb") as file:
            decompressed = bz2.decompress(file.read())
            with open(file_location, "wb") as file:
                file.write(decompressed)
        os.remove(file_server_location)

    def get_file_sha1(self, file_location: Path):
        hasher = hashlib.sha1()
        with open(file_location, "rb") as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    def download_game_files(self):
        if not self.game_path.exists():
            self.game_path.mkdir(parents=True, exist_ok=True)
        manifest = self.session.get(
            "https://cdn.toontownrewritten.com/content/patchmanifest.txt"
        ).json()
        keys = list(manifest.keys())
        for key in keys:
            if self.os not in manifest[key]["only"]:
                del manifest[key]
        progress_bar = tqdm(
            manifest.keys(),
            leave=False,
        )
        for file in manifest.keys():
            progress_bar.set_description(file)
            file_server = manifest[file]["dl"]
            file_location = self.game_path / file
            if not file_location.exists():
                self.download_game_file(file_server, file_location)
            else:
                file_sha1 = self.get_file_sha1(file_location)
                if file_sha1 != manifest[file]["hash"]:
                    self.download_game_file(file_server, file_location)
            progress_bar.update()
        progress_bar.close()

    def login_request(
        self,
        toon_guard_input: str = "",
        toon_guard_token: str = "",
        queue_token: str = "",
    ):
        data = {}
        params = {
            "format": "json",
        }
        if toon_guard_input:
            params["appToken"] = toon_guard_input
            params["authToken"] = toon_guard_token
        else:
            data["username"] = self.username
            data["password"] = self.password
        if queue_token:
            data["queueToken"] = queue_token
        response = self.session.post(
            "https://www.toontownrewritten.com/api/login",
            params=params,
            data=data,
        )
        response.raise_for_status()
        response = response.json()
        if response["success"] == "false":
            raise Exception(response["banner"])
        return response

    def get_play_cookie(self):
        login_response = self.login_request()
        while login_response["success"] == "partial":
            toon_guard_input = input(f'{login_response["banner"]}: ')
            login_response = self.login_request(
                toon_guard_input=toon_guard_input,
                toon_guard_token=login_response["responseToken"],
            )
        while login_response["success"] == "delayed":
            login_response = self.login_request(
                queue_token=login_response["queueToken"]
            )
            time.sleep(5)
        return login_response["cookie"], login_response["gameserver"]

    def launch_game(self, play_cookie, game_server):
        os.environ["TTR_PLAYCOOKIE"] = play_cookie
        os.environ["TTR_GAMESERVER"] = game_server
        os.chdir(self.game_path)
        if self.enable_log:
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


class Config:
    def __init__(self):
        self.config_path = Path.home() / ".gttrl"
        self.config_location = self.config_path / "config.json"

    def create_if_not_exists(self):
        if not self.config_path.exists():
            self.config_path.mkdir(parents=True, exist_ok=True)
        if not self.config_location.exists():
            with open(self.config_location, "w") as f:
                json.dump(
                    {
                        "game_path": str(self.config_path / "Toontown Rewritten"),
                        "skip_update": False,
                        "enable_log": False,
                        "account_file": str(self.config_path / "account.txt"),
                    },
                    f,
                    indent=4,
                )

    def read_config_file(self):
        with open(self.config_location, "r") as f:
            return json.load(f)
