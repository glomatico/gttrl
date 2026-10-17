"""TTR's documented password, 2FA/ToonGuard, and queue authentication flow."""

from __future__ import annotations

import time
from collections.abc import Callable

import click
import httpx

from .models import LoginResponse

LOGIN_API_URL = "https://www.toontownrewritten.com/api/login"


class LoginError(click.ClickException):
    pass


class AuthClient:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=20.0)
        self.owns_client = client is None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.owns_client:
            self.client.close()

    def _post(self, data: dict[str, str]) -> dict:
        try:
            response = self.client.post(
                LOGIN_API_URL,
                params={"format": "json"},
                data=data,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise LoginError(f"Unable to contact the TTR login API: {error}") from error
        if not isinstance(payload, dict) or payload.get("success") not in {
            "true", "false", "partial", "delayed"
        }:
            raise LoginError("Unexpected response from the TTR login API")
        return payload

    def login(
        self,
        username: str,
        password: str,
        *,
        prompt_token: Callable[[str], str] | None = None,
        display: Callable[[str], None] = click.echo,
        sleep: Callable[[float], None] = time.sleep,
    ) -> LoginResponse:
        prompt_token = prompt_token or (lambda banner: click.prompt(banner, hide_input=True))
        response = self._post({"username": username, "password": password})
        queue_token = None
        while True:
            state = response["success"]
            if state == "false":
                raise LoginError(str(response.get("banner") or "Login failed"))
            if state == "true":
                cookie = response.get("cookie")
                server = response.get("gameserver")
                if not isinstance(cookie, str) or not cookie or not isinstance(server, str) or not server:
                    raise LoginError("Login succeeded but the server did not provide game credentials")
                return LoginResponse(cookie, server, response.get("manifest"))
            if state == "partial":
                token = response.get("responseToken")
                if not isinstance(token, str) or not token:
                    raise LoginError("Authentication challenge has no responseToken")
                challenge = prompt_token(str(response.get("banner") or "Authentication code"))
                if not challenge:
                    raise LoginError("Authentication code cannot be empty")
                response = self._post({"appToken": challenge, "authToken": token})
                continue
            queue_token = response.get("queueToken") or queue_token
            if not isinstance(queue_token, str) or not queue_token:
                raise LoginError("Login queue did not provide a token")
            eta = response.get("eta", "3")
            try:
                delay = max(3, min(int(eta), 30))
            except (TypeError, ValueError):
                delay = 3
            display(f"Queue position: {response.get('position', '?')} (ETA: {eta}s)")
            sleep(delay)
            response = self._post({"queueToken": queue_token})
