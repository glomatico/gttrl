import json
import os

import pytest
from click import ClickException

from gttrl.config import Config, _account


def test_new_config_and_permissions(tmp_path):
    path = tmp_path / "config.json"
    config = Config(path)
    assert config.get("concurrent_downloads") == 3
    assert config.get("accounts") == []
    assert json.loads(path.read_text())["account_wizard"] is True
    config.set("account_wizard", False)
    assert Config(path).get("account_wizard") is False
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_legacy_settings_are_preserved(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"skip_update": true, "game_dir_path": "/tmp/ttr"}')
    config = Config(path)
    assert config.get("skip_update") is True
    assert config.get("game_dir_path") == "/tmp/ttr"
    assert config.get("accounts") == []


def test_migrates_v14_launcher_options_without_writing_on_read(tmp_path):
    path = tmp_path / "config.json"
    legacy = {
        "login_mode": "playcookieandgameserver",
        "skip_update": True,
        "display_game_log": True,
        "game_dir_path": "/old/game",
    }
    path.write_text(json.dumps(legacy))
    config = Config(path)
    assert config.get("accounts") == []
    assert config.get("ask_play_cookie") is True
    assert config.get("skip_update") is True
    assert config.get("display_game_log") is True
    assert config.get("game_dir_path") == "/old/game"
    assert json.loads(path.read_text()) == legacy
    config.set("skip_update", False)
    stored = json.loads(path.read_text())
    assert stored["ask_play_cookie"] is True
    assert stored["skip_update"] is False
    assert "login_mode" not in stored


def test_v14_default_credentials_mode_remains_credentials(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "login_mode": "credentials", "skip_update": True,
    }))
    assert Config(path).get("ask_play_cookie") is False


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
        config.set("accounts", [_account("alice")])


def test_new_accounts_schema_and_validation(tmp_path):
    path = tmp_path / "config.json"
    config = Config(path)
    config.set("accounts", [
        _account("long-email@example.com", alias="MyToon", auto_launch=True, save_password=False),
        _account("secondary", save_password=True),
    ])
    assert Config(path).get("accounts")[0]["alias"] == "MyToon"
    contents = path.read_text()
    assert '"auto_login_accounts"' not in contents
    assert '"auto_launch": true' in contents
    for invalid in [
        [{"username": "abc", "password": "secret"}],
        [_account("abc", save_password=True), _account("abc", save_password=False)],
        [_account("abc", alias="secondary"), _account("secondary")],
        [{**_account("abc"), "save_password": "other"}],
        [{**_account("abc"), "auto_launch": "yes"}],
        [{**_account("abc"), "alias": "two words"}],
    ]:
        with pytest.raises(ClickException):
            config.set("accounts", invalid)


@pytest.mark.parametrize("obsolete", [
    ["toon@example.com"],
    [{"username": "toon@example.com", "alias": None, "auto_login": True, "save_password": "yes"}],
    [{"username": "toon@example.com", "alias": None, "auto_launch": True, "save_password": "ask"}],
])
def test_intermediate_2_0_account_formats_are_not_migrated(tmp_path, obsolete):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"accounts": obsolete}))
    with pytest.raises(ClickException):
        Config(path)


def test_v14_config_never_imports_secret_fields(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "login_mode": "credentials",
        "username": "legacy@example.com", "password": "private-secret",
    }))
    config = Config(path)
    config.set("ask_play_cookie", False)
    data = json.loads(path.read_text())
    assert "username" not in data
    assert "password" not in data
    assert "private-secret" not in path.read_text()
