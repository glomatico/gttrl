# Glomatico's Toontown Rewritten Launcher
A cross-platform CLI launcher for Toontown Rewritten written in Python and installable via pip.

## Setup
1. Install Python 3.7 or higher.
2. Install with pip:
    ```
    pip install gttrl
    ```
3. Run on the command line:
    ```
    gttrl
    ```
    or specify your account credentials using arguments:
    ```
    gttrl -u username -p password
    ```

## Launcher folder
Once you run the launcher, a folder will be created at `<user home directory>/.gttrl` to store the configuration file and the game files.

## Configuration
You can configure the launcher by editing the `config.json` file in the launcher folder.

## Auto login
To enable auto login, create a file named `account.txt` in the launcher folder and put your account credentials in it, separated by a newline:
```
username
password
```

## Usage
```
usage: gttrl [-h] [-u USERNAME] [-p PASSWORD] [-a ACCOUNT_FILE]
                   [-m GAME_PATH] [-c PLAY_COOKIE] [-g GAME_SERVER] [-s] [-k]
                   [-e] [-v]

Glomatico's Toontown Rewritten Launcher

options:
  -h, --help            show this help message and exit
  -u USERNAME, --username USERNAME
                        Account username
  -p PASSWORD, --password PASSWORD
                        Account password
  -a ACCOUNT_FILE, --account-file ACCOUNT_FILE
                        Account file location
  -m GAME_PATH, --game-path GAME_PATH
                        Game path
  -c PLAY_COOKIE, --play-cookie PLAY_COOKIE
                        Play cookie
  -g GAME_SERVER, --game-server GAME_SERVER
                        Game server
  -s, --skip-update     Skip game update
  -k, --print-play-cookie
                        Print play cookie and game server and exit
  -e, --enable-log      Enable logging to the console
  -v, --version         show program's version number and exit
```
