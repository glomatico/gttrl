# Glomatico's Toontown Rewritten Launcher
A cross-platform CLI launcher for Toontown Rewritten.
  
## Features
* Cross-platform
* Lightweight and fast
* Easy to install and use
* Highly configurable
  
## Prerequisites
* Python 3.8 or higher
  
## Installation
1. Install the package `gttrl` using pip
    ```bash
    pip install gttrl
    ```

## Usage
```bash
gttrl [OPTIONS]
```
gttrl will prompt the username and password if they are not provided through the command line arguments. After logging in, it will check for game updates and download them if necessary. Finally, it will launch the game.

## Configuration
gttrl can be configured by using the command line arguments or the config file.

The config file is created automatically when you run gamdl for the first time at `~/.gttrl/config.json` on Linux and `%USERPROFILE%\.gttrl\config.json` on Windows.

Config file values can be overridden using command line arguments.

| Command line argument / Config file key                                     | Description                                 | Default value               |
| --------------------------------------------------------------------------- | ------------------------------------------- | --------------------------- |
| `--username`, `-u` / -                                                      | Username.                                   | `null`                      |
| `--password`, `-p` / -                                                      | Password.                                   | `null`                      |
| `--play-cookie` / -                                                         | Play cookie.                                | `null`                      |
| `--game-server` / -                                                         | Game server.                                | `null`                      |
| `--login-mode` / `login_mode`                                               | Login mode.                                 | `credentials`               |
| `--print-play-cookie-and-game-server` / `print_play_cookie_and_game_server` | Print play cookie and game server and exit. | `false`                     |
| `--skip-update` / `skip_update`                                             | Skip checking for game updates.             | `false`                     |
| `--config-path` / -                                                         | Path to the config file.                    | `<home>/.gttrl/config.json` |
| `--game-dir-path` / `game_dir_path`                                         | Path to the game directory.                 | `<home>/.gttrl/game`        |
| `--display-game-log` / `display_game_log`                                   | Display game log on terminal.               | `false`                     |
| `--no-config-file`, `-n` / -                                                | Don't load the config file.                 | `false`                     |

### Login modes
The following login modes are available:
* `credentials`
  * Manually enter your account credentials or read from the command line arguments.
* `playcookieandgameserver`
  * Manually enter a play cookie and game server or read from the command line arguments. You grab a play cookie and game server by enabling the `print_play_cookie_and_server` option using `credentials` login mode. This is useful when you want to allow someone else to play without sharing your account credentials.
