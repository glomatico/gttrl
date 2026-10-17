# Changelog

## 2.0.0 (unreleased)

- Redesign CLI around `gttrl`, `gttrl play`, `gttrl accounts`, and `gttrl config`.
- Restore an explicit `--login-mode` selector alongside automatic detection;
  prompt for missing play-cookie or game-server values when interactive.
- Add securely remembered accounts with separate auto-login and save-prompt preferences.
- Support multi-toon auto-login: choose several saved accounts and launch a
  separate game instance for each, reusing a single update check.
- Migrate existing single-account auto-login preferences without changing the
  previous default account.
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
