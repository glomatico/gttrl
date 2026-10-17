import pytest

from gttrl.config import Config
from gttrl.credentials import Accounts, CredentialError


def test_saved_accounts_and_auto_login(tmp_path, monkeypatch):
    passwords = {}
    monkeypatch.setattr("gttrl.credentials.keyring.get_keyring", lambda: type("Backend", (), {"priority": 1})())
    monkeypatch.setattr("gttrl.credentials.keyring.set_password", lambda service, name, password: passwords.__setitem__(name, password))
    monkeypatch.setattr("gttrl.credentials.keyring.get_password", lambda service, name: passwords.get(name))
    monkeypatch.setattr("gttrl.credentials.keyring.delete_password", lambda service, name: passwords.pop(name))
    config = Config(tmp_path / "config.json")
    accounts = Accounts(config)
    accounts.add("toon1", "secret1", auto_login=True)
    accounts.add("toon2", "secret2", auto_login=False)
    assert accounts.usernames == ["toon1", "toon2"]
    assert config.get("default_account") == "toon1"
    assert config.get("auto_login") is False
    assert accounts.get("toon1") == "secret1"
    assert "secret1" not in config.path.read_text()
    accounts.remove("toon1")
    assert accounts.usernames == ["toon2"]
    assert config.get("default_account") == "toon2"
    assert passwords == {"toon2": "secret2"}


def test_no_insecure_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr("gttrl.credentials.keyring.get_keyring", lambda: type("Backend", (), {"priority": 0})())
    config = Config(tmp_path / "config.json")
    with pytest.raises(CredentialError, match="No secure OS keyring"):
        Accounts(config).add("toon", "password")
    assert config.get("accounts") == []
