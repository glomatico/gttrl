import httpx
import pytest

from gttrl.auth import AuthClient, LoginError


def test_repeated_2fa_and_queue_without_repeated_token():
    replies = iter([
        {"success": "partial", "banner": "Authenticator", "responseToken": "challenge1"},
        {"success": "partial", "banner": "Email code", "responseToken": "challenge2"},
        {"success": "delayed", "queueToken": "queue1", "position": "5", "eta": "80"},
        {"success": "delayed", "position": "2", "eta": "1"},
        {
            "success": "true",
            "cookie": "cookie",
            "gameserver": "server",
            "manifest": "/content/patchmanifest.txt",
        },
    ])
    requests = []

    def handler(request):
        requests.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json=next(replies))

    sleeps = []
    banners = []
    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        AuthClient(client) as auth,
    ):
        result = auth.login(
            "user", "password",
            prompt_token=lambda banner: banners.append(banner) or "123456",
            sleep=sleeps.append,
        )
    assert result.manifest == "/content/patchmanifest.txt"
    assert result.play_cookie == "cookie"
    assert banners == ["Authenticator", "Email code"]
    assert sleeps == [30, 3]
    assert requests[-1]["queueToken"] == "queue1"
    assert requests[1]["authToken"] == "challenge1"
    assert requests[2]["authToken"] == "challenge2"


@pytest.mark.parametrize("response", [
    {"success": "false", "banner": "Invalid credentials"},
    {"success": "true"},
    {"success": "unexpected"},
    {"success": "partial"},
    {"success": "delayed"},
])
def test_bad_login_response(response):
    with (
        httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response))) as client,
        AuthClient(client) as auth,
        pytest.raises(LoginError),
    ):
        auth.login("user", "password")
