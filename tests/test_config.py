import json
import os

import pytest
from click import ClickException

from gttrl.config import Config


def test_new_config_and_permissions(tmp_path):
    path = tmp_path / "config.json"
    config = Config(path)
    assert config.get("concurrent_downloads") == 3
    assert config.get("auto_login") is False
    assert json.loads(path.read_text())["save_prompt"] == "ask"
    config.set("save_prompt", "never")
    assert Config(path).get("save_prompt") == "never"
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_legacy_settings_are_preserved(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"skip_update": true, "game_dir_path": "/tmp/ttr"}')
    config = Config(path)
    assert config.get("skip_update") is True
    assert config.get("game_dir_path") == "/tmp/ttr"
    assert config.get("accounts") == []


def test_migrates_legacy_single_auto_login_without_writing_on_read(tmp_path):
    path = tmp_path / "config.json"
    legacy = {
        "accounts": ["alice", "bob"], "default_account": "alice",
        "auto_login": True, "skip_update": True,
    }
    path.write_text(json.dumps(legacy))
    config = Config(path)
    assert config.get("auto_login_accounts") == ["alice"]
    assert json.loads(path.read_text()) == legacy
    config.set("skip_update", False)
    assert Config(path).get("auto_login_accounts") == ["alice"]


def test_new_auto_login_config_does_not_reenable_legacy_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "accounts": ["alice"], "auto_login": True,
        "default_account": "alice", "auto_login_accounts": [],
    }))
    assert Config(path).get("auto_login_accounts") == []
    assert Config(path).get("auto_login") is False


@pytest.mark.parametrize("contents", ["not json", "[]", '{"concurrent_downloads": 0}'])
def test_invalid_config_reports_error(tmp_path, contents):
    path = tmp_path / "config.json"
    path.write_text(contents)
    with pytest.raises(ClickException):
        Config(path)


def test_no_config_file_does_not_write(tmp_path):
    path = tmp_path / "config.json"
    config = Config(path, disabled=True)
    assert not path.exists()
    with pytest.raises(ClickException):
        config.set("auto_login", True)
