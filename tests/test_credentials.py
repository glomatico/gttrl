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
    accounts.add("toon1", "secret1", auto_launch=True)
    accounts.add("toon2", "secret2", auto_launch=False)
    assert accounts.usernames == ["toon1", "toon2"]
    assert "default_account" not in config.data
    assert config.get("accounts")[0]["auto_launch"] is True
    assert accounts.auto_launch_accounts == ["toon1"]
    assert accounts.get("toon1") == "secret1"
    assert "secret1" not in config.path.read_text()
    accounts.remove("toon1")
    assert accounts.usernames == ["toon2"]
    assert "default_account" not in config.data
    assert config.get("accounts")[0]["auto_launch"] is False
    assert passwords == {"toon2": "secret2"}


def test_select_multiple_accounts_and_preserve_choices(tmp_path, monkeypatch):
    passwords = {}
    monkeypatch.setattr("gttrl.credentials.keyring.get_keyring", lambda: type("Backend", (), {"priority": 1})())
    monkeypatch.setattr("gttrl.credentials.keyring.set_password", lambda service, name, password: passwords.__setitem__(name, password))
    monkeypatch.setattr("gttrl.credentials.keyring.get_password", lambda service, name: passwords.get(name))
    monkeypatch.setattr("gttrl.credentials.keyring.delete_password", lambda service, name: passwords.pop(name))
    accounts = Accounts(Config(tmp_path / "config.json"))
    accounts.add("alice", "pw1", auto_launch=True)
    accounts.add("bob", "pw2", auto_launch=False)
    assert accounts.auto_launch_accounts == ["alice"]
    accounts.set_auto_launch(["alice", "bob"])
    accounts.add("charlie", "pw3", auto_launch=False)
    assert accounts.auto_launch_accounts == ["alice", "bob"]
    accounts.update_password("alice", "new-password")
    assert passwords["alice"] == "new-password"
    assert accounts.auto_launch_accounts == ["alice", "bob"]
    accounts.remove("alice")
    assert accounts.auto_launch_accounts == ["bob"]
    with pytest.raises(CredentialError, match="No saved account"):
        accounts.set_auto_launch(["nonexistent"])
    assert accounts.auto_launch_accounts == ["bob"]


def test_exclusive_auto_login_replaces_selected_accounts(tmp_path, monkeypatch):
    passwords = {}
    monkeypatch.setattr("gttrl.credentials.keyring.get_keyring", lambda: type("Backend", (), {"priority": 1})())
    monkeypatch.setattr("gttrl.credentials.keyring.set_password", lambda service, name, password: passwords.__setitem__(name, password))
    accounts = Accounts(Config(tmp_path / "config.json"))
    accounts.add("alice", "first", auto_launch=True)
    accounts.add("bob", "second", auto_launch=True)
    assert accounts.auto_launch_accounts == ["alice", "bob"]
    accounts.add("charlie", "third", auto_launch=True, exclusive_auto_launch=True)
    assert accounts.auto_launch_accounts == ["charlie"]
    assert accounts.usernames == ["alice", "bob", "charlie"]
    assert passwords == {"alice": "first", "bob": "second", "charlie": "third"}
    with pytest.raises(CredentialError, match="requires auto_launch"):
        accounts.add("invalid", "password", exclusive_auto_launch=True)
    assert "invalid" not in passwords


def test_no_insecure_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr("gttrl.credentials.keyring.get_keyring", lambda: type("Backend", (), {"priority": 0})())
    config = Config(tmp_path / "config.json")
    with pytest.raises(CredentialError, match="No secure OS keyring"):
        Accounts(config).add("toon", "password")
    assert config.get("accounts") == []


def test_explicit_no_auto_launch_overrides_existing_preference(tmp_path, monkeypatch):
    passwords = {}
    monkeypatch.setattr("gttrl.credentials.keyring.get_keyring", lambda: type("Backend", (), {"priority": 1})())
    monkeypatch.setattr("gttrl.credentials.keyring.set_password", lambda service, name, password: passwords.__setitem__(name, password))
    accounts = Accounts(Config(tmp_path / "config.json"))
    accounts.add("toon", "password", auto_launch=True)
    assert accounts.auto_launch_accounts == ["toon"]
    accounts.add("toon", "new-password", auto_launch=False)
    assert accounts.auto_launch_accounts == []
    assert passwords["toon"] == "new-password"


def test_insecure_third_party_keyring_rejected(tmp_path, monkeypatch):
    # A positive priority alone must not allow a plaintext keyrings.alt backend.
    Backend = type("Plaintext", (), {"priority": 1})
    Backend.__module__ = "keyrings.alt.file"
    monkeypatch.setattr("gttrl.credentials.keyring.get_keyring", lambda: Backend())
    with pytest.raises(CredentialError, match="insecure"):
        Accounts(Config(tmp_path / "config.json")).add("toon", "secret")
