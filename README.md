# GTTRL — Glomatico's Toontown Rewritten Launcher

A lightweight, cross-platform command-line launcher for [Toontown Rewritten](https://www.toontownrewritten.com/), with secure remembered accounts, interactive login, and concurrent game updates.

Interactive prompts use Questionary; human-facing status messages, account tables,
and download progress use Rich. Machine-readable output remains plain text.

> GTTRL is an unofficial community project and is not affiliated with the Toontown Rewritten team.

## Features

- **Multi-toon / multi-login:** select several remembered accounts and start a separate
  Toontown Rewritten instance for each with a single `gttrl` command.
- **Secure account management:** per-account CLI aliases, auto-launch preferences,
  and password policies. Passwords are stored in the system keyring only when
  the account is configured to use it.
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
gttrl play --accounts toon1 toon2      # Launch only these aliases
gttrl play --accounts toon1,toon2     # Comma-separated works too
gttrl play --choose-account
gttrl play --no-saved-login
gttrl play --no-account-wizard        # Override config for this run
```

With no account remembered, GTTRL prompts for a username and password.
After a successful login, the setup wizard asks:

1. **Remember this account?** Yes / No. Choosing No skips all remaining questions and doesn't store anything.
2. **Account alias?** Optional, with no spaces.
3. **Enable auto-launch?** Yes / No. Automatically selects this account for launching, independently of its password.
4. **Remember the password?** Yes / No. Yes stores the password securely in the OS keyring.

Auto-launch and password saving are independent: with auto-launch enabled but
password saving disabled, GTTRL selects the account and still asks for its
password. TTR may also require 2FA/ToonGuard.

The global `account_wizard` preference controls only the account setup flow.
When disabled, use `gttrl --username USER --password-stdin` for manual
login without registration questions. Previously configured accounts,
saved-password policies, and multi-login continue to work unchanged.
CLI arguments override saved settings without rewriting the configuration.
To re-enable the setup wizard:

```sh
gttrl config set account-wizard true
```

### Saved accounts

```sh
gttrl accounts add
gttrl accounts add --username myuser --auto-launch
gttrl accounts                          # Interactive account manager
gttrl accounts add --username user@example.com --alias toon1 --no-save-password
gttrl accounts list
gttrl accounts alias myuser toon1
gttrl accounts alias myuser --clear
gttrl accounts save-password myuser enable
gttrl accounts save-password myuser disable
gttrl accounts auto-launch on
gttrl accounts auto-launch off
gttrl accounts remove myuser
gttrl accounts clear
```

`accounts add` validates credentials with TTR before registering the account.
`save_password` is a boolean:

- **`true`:** use the OS keyring. If the secret is missing, GTTRL prompts for
  a password; after successful authentication it saves the password in the
  keyring, so subsequent launches don't ask again. Rejected saved passwords
  can also be replaced after a successful retry.
- **`false`:** always ask for a password without retrieving it from the
  keyring. Disabling password saving through the account manager deletes the
  existing keyring secret.

Passwords are stored via [keyring](https://pypi.org/project/keyring/) **only
when enabled**, not in the JSON file. Aliases are optional, unique,
whitespace-free account identifiers: when `alias` is null, GTTRL displays
the username. Commands such as `gttrl play --accounts toon1 toon2` accept
aliases or usernames, and explicitly select which accounts to launch.
No insecure plaintext password fallback is used.

Running `gttrl accounts` without a subcommand opens an interactive editor:
choose a saved account to edit its password, password-saving behavior, alias,
auto-launch selection, or remove it. Editing a password warns that it will
overwrite/save the keyring secret and verifies authentication before doing so.
Auto-launch and password-saving menus offer **Enable / Disable / Back**.
The manager is available even when `account_wizard` is disabled.

### Multi-toon / multi-login

To automatically start multiple game instances, select which saved accounts
should log in when running `gttrl`:

```sh
gttrl accounts add                        # Add your additional TTR accounts
gttrl accounts add --exclusive-auto-launch # Auto-launch only this account
gttrl accounts add --auto-launch           # Add account to auto-launch
gttrl accounts add --no-auto-launch        # Save without auto-launching
gttrl accounts auto-launch                 # Interactive multi-select menu
gttrl accounts auto-launch set alice bob   # Non-interactive selection
gttrl accounts auto-launch list            # Show selected usernames
gttrl accounts auto-launch off             # Disable auto-launch
gttrl accounts auto-launch on              # Enable first saved account if none selected
gttrl                                     # Start one game instance per selected account
```

Existing configurations with string usernames and global auto-login fields
are migrated in memory and written using the new account format on the next
configuration change. Old `auto_login` preferences migrate to `auto_launch`;
old `save_password: "yes"` becomes `true`, and `"ask"`/`"never"` become
`false`. Previously saved passwords are not rewritten during migration.
Adding accounts does not disable existing auto-launch selections.
Use `gttrl play --account alice` to explicitly launch **one** account even
when multi-login is enabled. `gttrl play --choose-account` forces the single-account
picker. Each selected account gets its own authenticated session and game
process; the shared game installation is checked and updated **only once**.
If no accounts are selected for auto-launch, `gttrl` shows the account picker.
The `--accounts` option overrides every saved auto-launch selection for that run.
When `--display-game-log` is enabled, output from multiple processes may interleave.

If a saved login is rejected by TTR, interactive sessions offer to re-enter the
password, skip that account, or cancel. A successfully reauthenticated account
with password saving enabled automatically updates its keyring entry.
Network failures are not treated as invalid passwords.

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

The account records in `~/.gttrl/config.json` now look like this:

```json
{
  "account_wizard": true,
  "accounts": [
    {
      "username": "complicated.email@example.com",
      "alias": "toon1",
      "auto_launch": true,
      "save_password": true
    },
    {
      "username": "second-account",
      "alias": null,
      "auto_launch": true,
      "save_password": false
    }
  ]
}
```

This is an excerpt showing only `accounts`. The real file also holds
non-sensitive settings, such as game directory and download concurrency. No
passwords appear in JSON. The global `account_wizard` switch controls
whether GTTRL offers to register previously unknown accounts.

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
