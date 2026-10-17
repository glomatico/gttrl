"""Rich presentation must remain safe for both players and scripts."""

import io

from click.testing import CliRunner
from rich.console import Console

from gttrl import ui
from gttrl.cli import main


def test_rich_messages_style_terminal_output(monkeypatch):
    stdout, stderr = io.StringIO(), io.StringIO()
    stderr_stream = stderr
    monkeypatch.setattr(
        ui, "console", lambda *, stderr=False: Console(
            file=stderr_stream if stderr else stdout,
            force_terminal=True,
            color_system="standard",
            no_color=False,
            width=90,
            highlight=False,
            markup=False,
        ),
    )
    ui.success("Saved [account] securely.")
    ui.warning("Deprecated option")
    ui.error("Cannot save credential")
    assert "\x1b[" in stdout.getvalue()
    assert "Saved [account] securely." in stdout.getvalue()
    assert "Deprecated option" in stderr.getvalue()
    assert "Cannot save credential" in stderr.getvalue()


def test_interactive_accounts_table(monkeypatch):
    buffer = io.StringIO()
    console = Console(file=buffer, width=80, force_terminal=True, color_system=None)
    monkeypatch.setattr(ui, "console", lambda *, stderr=False: console)
    ui.accounts_list(
        ["my[toon]", "other"], auto_login=True
    )
    output = buffer.getvalue()
    assert "Saved Accounts" in output
    assert "my[toon]" in output
    assert "other" in output
    assert "Auto-login: on" in output


def test_script_friendly_account_listing(tmp_path):
    from gttrl.config import Config, _account

    path = tmp_path / "config.json"
    settings = Config(path)
    settings.set("accounts", [_account("toon1"), _account("toon2")])
    result = CliRunner().invoke(main, [
        "accounts", "--config-path", str(path), "list"
    ])
    assert result.exit_code == 0, result.output
    assert result.output == "toon1\ntoon2\nAuto-login: off\n"
    assert "\x1b[" not in result.output


def test_config_get_stays_plain(tmp_path):
    result = CliRunner().invoke(main, [
        "config", "--config-path", str(tmp_path / "config.json"),
        "get", "concurrent-downloads"
    ])
    assert result.exit_code == 0
    assert result.output == "3\n"
