# Glomatico's Toontown Rewritten Launcher

A cross-platform CLI launcher for Toontown Rewritten written in Python and installable via pip.

## Table of contents
- [Glomatico's Toontown Rewritten Launcher](#glomaticos-toontown-rewritten-launcher)
  - [Table of contents](#table-of-contents)
  - [Features](#features)
  - [Installation](#installation)
  - [Usage](#usage)
  - [Configuration](#configuration)
    - [Login modes](#login-modes)
  
## Features
- Cross-platform
- Auto login with accounts stored in a file
- Lightweight and fast
- Easy to install and use
- Highly configurable
  
## Installation
1. Install Python 3.7 or higher
  
2. Install gttrl using pip:

    ```bash
    pip install gttrl
    ```

## Usage
To run the launcher, simply execute the following command:

```bash
gttrl
```

## Configuration
gttrl can be configured using the command line arguments or the config file. The config file is created automatically when you run gttrl for the first time at `~/.gttrl/config.json` on Linux and `%USERPROFILE%\.gttrl\config.json` on Windows. Config file values can be overridden using command line arguments.

| Command line argument / Config file key | Description | Default value |
| --- | --- | --- |
| `-l`, `--login-mode` / `login_mode` | Login mode to use. | `credentials` |
| `-u`, `--username` / - | Account username. | `null` |
| `-p`, `--password` / - | Account password. | `null` |
| `-a`, `--account-name` / `account_name` | Account name provided in accounts file. | `null` |
| `--accounts-file-path` / `accounts_file_path` | Path to a .ini file containing account credentials | `<home folder>/.gttrl/accounts.ini` |
| `--play-cookie` / - | Play cookie. | `null` |
| `--game-server` / - | Game server. | `null` |
| `--config-file-path` / - | Path to a .json file containing the launcher configuration. | `<home folder>/.gttrl/config.json` |
| `--game-dir-path` / `game_dir_path` | Path to Toontown Rewritten game directory. | `<home folder>/.gttrl/Toontown Rewritten` |
| `--no-config-file` / - | Don't read from config file and don't write the default config file. | `false` |
| `--display-game-log` / `display_game_log` | Display the game log in the terminal. | `false` |
| `-s`, `--skip-update` / `skip_update` | Skip checking for game updates. | `false` |
| `--print-play-cookie-and-server` / `print_play_cookie_and_server` | Print the play cookie and game server and exit. | `false` |

### Login modes

If you don't provide the necessary values for a login mode, either through the command line or the config file, you will be prompted to enter them.

- **`credentials`**: Manually enter your account credentials. This is the default login mode.
  
- **`accountsfile`**: Select an account from an accounts file. The accounts file must be in the following format:
  ```ini
  [account1]
  username=myusername
  password=mypassword

  [account2]
  ...
  ```

- **`playcookie`**: Manually enter a play cookie and game server. You can get your play cookie and game server by enabling the `print_play_cookie_and_server` option with one of the other login modes. In theory, you can share your play cookie and game server with other people to let them play on your account without giving them your username and password.
