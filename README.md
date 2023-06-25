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
    gttrl -u username -p password
    ```

## Account file
The account file is a text file with the following format:
```
username
password
```

## Usage
```
usage: gttrl [-h] [-u USERNAME] [-p PASSWORD] [-a ACCOUNT_FILE]
                   [-f GAME_PATH] [-c PLAY_COOKIE] [-g GAME_SERVER] [-s] [-k]
                   [-e] [-v]

Glomatico's Toontown Rewritten Launcher

options:
  -h, --help            show this help message and exit
  -u USERNAME, --username USERNAME
                        Account username (default: None)
  -p PASSWORD, --password PASSWORD
                        Account password (default: None)
  -a ACCOUNT_FILE, --account-file ACCOUNT_FILE
                        Account file location (default: ./account.txt)
  -f GAME_PATH, --game-path GAME_PATH
                        Game path (default: ./Toontown Rewritten)
  -c PLAY_COOKIE, --play-cookie PLAY_COOKIE
                        Play cookie (default: None)
  -g GAME_SERVER, --game-server GAME_SERVER
                        Game server (default: None)
  -s, --skip-update     Skip game update (default: False)
  -k, --print-play-cookie
                        Print play cookie and game server and exit (default:
                        False)
  -e, --enable-log      Enable log (default: False)
  -v, --version         show program's version number and exit
```
