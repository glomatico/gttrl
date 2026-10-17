# Changelog

## 2.0.0 (unreleased)

- Redesign CLI around `gttrl`, `gttrl play`, `gttrl accounts`, and `gttrl config`.
- Restore an explicit `--login-mode` selector alongside automatic detection;
  prompt for missing play-cookie or game-server values when interactive.
- Add securely remembered accounts with per-account auto-login and password preferences.
- Store alias, auto-login, and ask/never/yes password policy inside each
  account record, migrating old string-based accounts without touching keyring secrets.
- Support whitespace-free CLI aliases and `gttrl play --accounts toon1 toon2`
  to explicitly select multiple accounts, overriding saved auto-login choices.
- Replace global `default_account` and `save_prompt` with `account_wizard`,
  without disabling existing saved accounts when the wizard is off.
- Add an interactive `gttrl accounts` editor for aliases, password changes,
  save-password policies, auto-login, and removal, including optional alias setup.
- Support multi-toon auto-login: choose several saved accounts and launch a
  separate game instance for each, reusing a single update check.
- Migrate previous single-account auto-login preferences into per-account
  selections without requiring new keyring credentials.
- Offer saved-password reauthentication and secure keyring replacement on
  explicitly rejected logins.
- Preserve auto-login selections when adding or removing other accounts.
- Offer Exclusive auto-login, Add to auto-login, or Just add when
  remembering additional accounts, including a scriptable exclusive flag.
- Report missing game dependencies, startup failures, and nonzero exit codes.
- Implement repeated 2FA challenges, queue updates, and dynamic manifest selection.
- Add three concurrent, verified and atomic game file downloads (configurable).
- Add interactive prompts and Rich progress indicators.
- Use consistent Rich status messages and an interactive saved-accounts table without changing script output.
- Move project packaging and dependency management from Flit to uv/uv_build.
- Introduce regression tests, cross-platform CI, and trusted PyPI publishing.
- Require Python 3.11 or newer.

## 1.4

- Previous legacy CLI release.
