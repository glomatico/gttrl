from dataclasses import dataclass


@dataclass
class LoginResponse:
    play_cookie: str
    game_server: str
