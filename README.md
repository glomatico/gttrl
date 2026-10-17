# GTTRL

**A simple command-line launcher for [Toontown Rewritten](https://www.toontownrewritten.com/).**

GTTRL lets you log in, keep your game up to date, and launch multiple Toons from one place. It works on **Windows, macOS, and Linux**.

> GTTRL is a fan-made project and isn't affiliated with the Toontown Rewritten team.

## What can GTTRL do?

- **Launch your game:** GTTRL signs you in and checks for game updates.
- **Remember your accounts:** Choose whether to remember each account and its password.
- **Play with multiple Toons:** Open a separate game window for each account you select.
- **Use short account names:** Give an account an alias like `toon1` instead of typing a long email address.
- **Keep your passwords safe:** When enabled, password saving uses your computer's secure password manager.

## Installation

You'll need **Python 3.11 or newer**.

Install GTTRL:

```sh
pip install gttrl
```

Or, if you use [uv](https://docs.astral.sh/uv/):

```sh
uv tool install gttrl
```

## Your first launch

Run:

```sh
gttrl
```

Enter your Toontown Rewritten username and password. After signing in, GTTRL can help you remember the account:

1. **Remember this account?** Choose **No** to play just this time, without any more setup questions.
2. **Account alias:** If you chose Yes, you can enter a short name such as `toon1`, or leave it blank.
3. **Enable auto-launch?** Choose Yes if you want GTTRL to launch this account automatically when you run `gttrl`.
4. **Remember the password?** Choose Yes to save it securely so you won't need to type it every time.

**Auto-launch doesn't require saving your password.** You can have GTTRL select an account automatically and still type its password each time.

If your saved password is missing, GTTRL asks for it and saves it after a successful login. Toontown Rewritten may still ask for a ToonGuard code.

## Manage your accounts

Run:

```sh
gttrl accounts
```

Choose an account from the menu to:

- Change its alias.
- Enable or disable auto-launch.
- **Enable password saving:** Enter and verify a password before saving or replacing it in your computer's password manager.
- **Disable password saving:** Remove its stored password and ask for it on future launches.
- Launch or remove the account.

You can also add a new account from this menu. The menu works even when the first-launch wizard is disabled.

## Play with multiple Toons

Give each account a short alias (for example, `toon1` and `toon2`), then run:

```sh
gttrl play --accounts toon1 toon2
```

GTTRL will launch a separate game window for each account. You can also choose just one:

```sh
gttrl play --account toon1
```

Normally, running `gttrl` launches every account with **auto-launch** enabled. Using `--account` or `--accounts` lets you choose who to launch **just this time**, without changing your saved choices.

If you'd rather choose accounts interactively, use:

```sh
gttrl play --choose-account
```

## Sign in without saving anything

For a one-time login, use:

```sh
gttrl --username you@example.com
```

GTTRL asks for your password, signs you in, and launches the game. **It won't start the account setup wizard**, even if the wizard is enabled.

You can supply both the username and password, too:

```sh
gttrl --username you@example.com --password YOUR_PASSWORD
```

However, typing a password into a command can expose it in your shell history. For scripts, `--password-stdin` is safer.

## Use a play cookie (advanced)

If you already have a play cookie and game server, you can launch the game without a normal account login.

```sh
gttrl --ask-play-cookie
```

This asks for both values. Or you can supply them:

```sh
gttrl --play-cookie COOKIE --game-server SERVER
```

If you provide only one, GTTRL asks for the other. To always use the prompts by default:

```sh
gttrl config set ask-play-cookie true
```

Providing `--username`, `--account`, or `--accounts` still chooses normal account login instead. Play cookies are temporary credentials and aren't saved.

## Change launcher settings

Some useful examples:

```sh
gttrl config show                           # View your settings
gttrl config set account-wizard false        # Stop offering account setup
gttrl config set ask-play-cookie false       # Use normal login by default
gttrl config set skip-update true            # Skip update checks
gttrl config set display-game-log true       # Show game messages
```

You can temporarily override saved settings with command options, such as `--check-update` or `--hide-game-log`. Your accounts are kept when you reset the launcher preferences.

GTTRL stores its settings in `~/.gttrl/config.json` (or `%USERPROFILE%\.gttrl\config.json` on Windows). Passwords are stored separately in your operating system's password manager, never in the JSON file.

If you're upgrading from **GTTRL 1.4**, your game-directory, update, and game-log settings are carried forward automatically.

## Need help?

- **Password manager unavailable?** You can still play without saving your password. On Linux, saving passwords usually requires an unlocked desktop keyring.
- **Game won't start?** Try `gttrl --display-game-log` to see more information.
- **No terminal for questions?** Supply your login details explicitly or use accounts with saved passwords.

See the [GitHub project](https://github.com/glomatico/gttrl) for issues, suggestions, and source code.

## License

GTTRL is available under the [MIT License](LICENSE).

## For developers

```sh
uv sync
uv run gttrl --help
uv run ruff check src tests
uv run pytest -q
uv build
```

Tests use simulated authentication and update responses. Before release, real account login, game updates, and multi-Toon launching should also be tested. PyPI releases use GitHub Actions trusted publishing.
