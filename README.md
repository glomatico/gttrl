# GTTRL — Glomatico's Toontown Rewritten Launcher

A lightweight, cross-platform command-line launcher for [Toontown Rewritten](https://www.toontownrewritten.com/), with secure remembered accounts, interactive login, and concurrent game updates.

Interactive prompts use Questionary; human-facing status messages, account tables,
and download progress use Rich. Machine-readable output remains plain text.

> GTTRL is an unofficial community project and is not affiliated with the Toontown Rewritten team.

## Features

- **Multi-toon / multi-login:** select several remembered accounts and start a separate
  Toontown Rewritten instance for each with a single `gttrl` command.
- **Secure account management:** passwords are stored in your system's credential
  manager, with optional automatic login and recovery when a saved login is rejected.
- **Multiple authentication methods:** username/password, saved accounts, or a
  manually supplied play cookie and game server, including ToonGuard/2FA support.
- **Fast, safe updates:** verify files, download up to three at a time, and
  atomically replace them only after checking their integrity.
- **Modern interactive CLI:** Questionary menus, Rich messages and progress
  bars, configurable settings, and scripting-friendly output.
- **Cross-platform:** runs on Linux, Windows and macOS with Python 3.11+.

## Requirements

- Python 3.11 or newer
- Windows, macOS, or Linux
- Internet connectivity for authentication and updates
- A supported OS credential manager **only if** you want to remember accounts (Windows Credential Manager, macOS Keychain, or a working desktop keyring on Linux)

## Install

Install the package using pip:

```sh
pip install gttrl
```

Or install it as a standalone tool with uv:

```sh
uv tool install gttrl
```

## Play

```sh
gttrl                  # Launch the game (same as gttrl play)
gttrl play             # Explicitly launch the game
gttrl play --account myuser
gttrl play --choose-account
gttrl play --no-saved-login
```

With no account remembered, GTTRL prompts for your username and password. After successful authentication, it offers to:

1. **Save and enable automatic login:** remember your account securely and add it to the accounts started automatically.
2. **Save but ask each time:** remember the account securely, but display an account picker when you run `gttrl`.
3. **Don't save:** use your credentials for this launch only.
4. **Never ask again:** don't save and suppress future save prompts.

If you turn on automatic login, you may **still be prompted for 2FA or ToonGuard** when Toontown Rewritten requires it.

To re-enable the save prompt after choosing Never:

```sh
gttrl config set save-prompt ask
```

### Saved accounts

```sh
gttrl accounts add
gttrl accounts add --username myuser --auto-login
gttrl accounts list
gttrl accounts default myuser
gttrl accounts auto-login on
gttrl accounts auto-login off
gttrl accounts remove myuser
gttrl accounts clear
```

`accounts add` validates the account by authenticating with the TTR login API before storing anything. Passwords are stored in the operating system's credential store via [keyring](https://pypi.org/project/keyring/); only account names and non-sensitive preferences are written to the JSON config. If no secure credential store is available, GTTRL **does not fall back to saving an unprotected password**.

### Multi-toon / multi-login

To automatically start multiple game instances, select which saved accounts
should log in when running `gttrl`:

```sh
gttrl accounts add                        # Add your additional TTR accounts
gttrl accounts add --exclusive-auto-login # Save and auto-launch only this account
gttrl accounts add --auto-login           # Add a saved account to auto-launch
gttrl accounts add --no-auto-login        # Save without changing auto-launch
gttrl accounts auto-login                 # Interactive multi-select menu
gttrl accounts auto-login set alice bob   # Non-interactive selection
gttrl accounts auto-login list            # Show selected usernames
gttrl accounts auto-login off             # Disable automatic login
gttrl accounts auto-login on              # Enable for your default account if none selected
gttrl                                     # Start one game instance per selected account
```

An existing 2.0 single-account auto-login configuration migrates automatically.
Adding other accounts does not disable or replace existing auto-login selections.
When adding another account interactively, GTTRL offers **Exclusive auto-login**
(replace the selected accounts with the new account), **Add to auto-login**
(launch it alongside those already selected), and **Just add** (keep the
existing selection unchanged). When saving a newly logged-in account, these
same options appear alongside **Don't save** and **Never ask again**.
Use `gttrl play --account alice` to explicitly launch **one** account even
when multi-login is enabled. `gttrl play --choose-account` forces the single-account
picker. Each selected account gets its own authenticated session and game
process; the shared game installation is checked and updated **only once**.
When `--display-game-log` is enabled, output from multiple processes may interleave.

If a saved login is rejected by TTR, interactive sessions offer to re-enter the
password, skip that account, or cancel. Once reauthentication succeeds, you
can replace its stored password. Network failures are not treated as invalid
passwords.

### Manual, external, and scripted login

```sh
gttrl play --username myuser                   # Prompt for password
gttrl play --username myuser --password-stdin  # Read password from stdin
gttrl play --play-cookie COOKIE --game-server HOST
gttrl play --login-mode play-cookie             # Prompt for both session values
gttrl play --game-server HOST                   # Prompt for the missing play cookie
gttrl play --play-cookie COOKIE                 # Prompt for the missing game server
gttrl play --login-mode credentials             # Explicit account login
```

For scripts, supply the password through a secure pipe or the system keyring. Avoid `--password` whenever possible, since command-line arguments and shell history can expose secrets.

Play cookies are temporary game-launch credentials, **not** reusable login tokens. They are never saved by GTTRL. The `--print-play-cookie-and-game-server` option explicitly prints sensitive session credentials; take care when redirecting its output.

The `--login-mode` option accepts `auto` (default), `credentials`, and
`play-cookie`. In automatic mode, providing either `--play-cookie` or
`--game-server` selects play-cookie login; any missing value is requested
interactively. Using `--login-mode play-cookie` prompts for both values if
neither was provided. The old `playcookieandgameserver` name remains accepted
as a legacy alias.

Account login options and play-cookie options cannot be mixed. In scripts
without an interactive terminal, missing values produce a clear error rather
than attempting to prompt.

## Updating the game

GTTRL verifies local files against the server's patch manifest, skips matching files, and downloads missing or outdated files concurrently. The default is **three simultaneous downloads**.

```sh
gttrl play --concurrent-downloads 5
gttrl config set concurrent-downloads 3
gttrl play --skip-update
gttrl play --check-update
```

Downloads are streamed to temporary files, decompressed in chunks, verified against the manifest's SHA-1 hashes, and then atomically moved into place. This prevents partial downloads from overwriting existing game files. Network timeouts and retries are enabled.

The login API provides the patch manifest path for authenticated sessions; externally supplied play cookies use the default public manifest.

## Configuration

Non-sensitive settings are kept in `~/.gttrl/config.json` (on Windows, `%USERPROFILE%\.gttrl\config.json`). Existing v1 settings such as `game_dir_path`, `skip_update`, and `display_game_log` remain supported.

```sh
gttrl config show
gttrl config get concurrent-downloads
gttrl config set game-dir-path "/path/to/game"
gttrl config reset
```

Settings accept booleans (`true`/`false`), integers, and text as appropriate. `gttrl config reset` preserves saved accounts. For one-off execution without reading or writing configuration, use `gttrl play --no-config-file`.

Play options override their saved equivalents. For example, `--check-update` overrides `skip_update=true`, while `--hide-game-log` overrides `display_game_log=true`.

## Development

GTTRL uses [uv](https://docs.astral.sh/uv/) for development and [uv_build](https://docs.astral.sh/uv/concepts/build-backend/) for packaging:

```sh
uv sync
uv run gttrl --help
uv run ruff check src tests
uv run pytest -q
uv build
```

The `tests/` suite mocks the TTR API and patch server. **Automated tests do not require a live TTR account.** Before publishing a release, manually test a real login, patch update, and game launch on supported platforms.

Publishing to PyPI uses GitHub Actions and OIDC trusted publishing. Configure the `pypi` environment and the trusted publisher for this repository in PyPI before publishing a release tagged `vX.Y.Z`.

## Troubleshooting

- **No secure OS keyring available:** Start your desktop keyring service (for example, Secret Service/KWallet on Linux), or choose not to save your account.
- **No interactive terminal:** Supply `--username` and `--password-stdin`, use `--account` with an accessible keyring, or provide both `--play-cookie` and `--game-server`.
- **Corrupted configuration:** Correct or move the JSON file at `~/.gttrl/config.json`. Credentials are kept separately in the OS keyring.
- **No game executable:** Ensure the game download completes successfully and `game_dir_path` points to the correct directory.
- **Game closes immediately:** Use `gttrl play --display-game-log` to inspect missing libraries or crash messages; multi-login uses separate processes with their own session credentials.
