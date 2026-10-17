"""Consistent human-facing terminal output, powered by Rich.

Machine-readable output (JSON, the play cookie and game server) stays with
Click so scripts receive plain text without decorative prefixes or ANSI codes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text


def console(*, stderr: bool = False) -> Console:
    # Construct on demand: CliRunner replaces stdout/stderr during an invocation.
    return Console(stderr=stderr, highlight=False, markup=False)


def _message(text: str, *, prefix: str, style: str, stderr: bool = False) -> None:
    output = Text()
    output.append(prefix, style=style)
    output.append(text)
    console(stderr=stderr).print(output)


def info(text: str) -> None:
    """Show a launcher status message."""
    _message(text, prefix="• ", style="cyan")


def success(text: str) -> None:
    """Show a successful operation."""
    _message(text, prefix="✓ ", style="green")


def warning(text: str) -> None:
    """Show a non-fatal warning on stderr."""
    _message(text, prefix="! ", style="yellow", stderr=True)


def error(text: str) -> None:
    """Show a non-fatal error on stderr."""
    _message(text, prefix="✗ ", style="red", stderr=True)


def accounts_list(
    usernames: Sequence[str],
    *,
    auto_login: bool,
    auto_login_accounts: Sequence[str] = (),
    aliases: Mapping[str, str | None] | None = None,
    password_policies: Mapping[str, str] | None = None,
) -> None:
    """Show a table to players and a stable, plain listing to scripts."""
    terminal = console().is_terminal
    aliases = aliases or {}
    password_policies = password_policies or {}
    if not usernames:
        if terminal:
            info("No saved accounts.")
        else:
            click.echo("No saved accounts.")
    elif terminal:
        table = Table(title="Saved Accounts", header_style="bold cyan")
        table.add_column("Account")
        table.add_column("Auto-login", justify="center")
        table.add_column("Password")
        for username in usernames:
            alias = aliases.get(username)
            title = f"{alias} ({username})" if alias else username
            table.add_row(
                Text(title),
                "✓" if username in auto_login_accounts else "",
                password_policies.get(username, ""),
            )
        console().print(table)
    else:
        for username in usernames:
            alias = aliases.get(username)
            display = f"{alias} ({username})" if alias else username
            label = ""
            if username in auto_login_accounts:
                label += " (auto-login)"
            click.echo(f"{display}{label}")
    summary = f"Auto-login: {'on' if auto_login else 'off'}"
    if terminal:
        info(summary)
    else:
        click.echo(summary)
