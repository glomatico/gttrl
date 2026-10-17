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


def test_migrates_legacy_single_auto_login_without_writing_on_read(tmp_path):
    path = tmp_path / "config.json"
    legacy = {
        "accounts": ["alice", "bob"], "default_account": "alice",
        "auto_login": True, "skip_update": True,
    }
    path.write_text(json.dumps(legacy))
    config = Config(path)
    assert config.get("accounts") == [
        _account("alice", auto_launch=True, save_password=True),
        _account("bob", save_password=True),
    ]
    assert json.loads(path.read_text()) == legacy
    config.set("skip_update", False)
    assert Config(path).get("accounts") == [
        _account("alice", auto_launch=True, save_password=True),
        _account("bob", save_password=True),
    ]
    assert "auto_login_accounts" not in json.loads(path.read_text())


def test_new_auto_login_config_does_not_reenable_legacy_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "accounts": ["alice"], "auto_login": True,
        "default_account": "alice", "auto_login_accounts": [],
    }))
    assert Config(path).get("accounts") == [
        _account("alice", auto_launch=False, save_password=True)
    ]


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


@pytest.mark.parametrize(
    ("old_policy", "expected"),
    [("yes", True), ("ask", False), ("never", False)],
)
def test_migrate_old_password_policies_and_autologin(
    tmp_path, old_policy, expected
):
    path = tmp_path / "config.json"
    old = {
        "account_wizard": True,
        "accounts": [{
            "username": "toon@example.com", "alias": "toon",
            "auto_login": True, "save_password": old_policy,
        }],
    }
    path.write_text(json.dumps(old))
    settings = Config(path)
    assert settings.get("accounts") == [
        _account("toon@example.com", alias="toon", auto_launch=True, save_password=expected)
    ]
    assert json.loads(path.read_text()) == old
    settings.set("skip_update", True)
    stored = json.loads(path.read_text())
    assert stored["accounts"][0]["auto_launch"] is True
    assert stored["accounts"][0]["save_password"] is expected
    assert "auto_login" not in stored["accounts"][0]
