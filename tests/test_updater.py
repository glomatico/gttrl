import asyncio
import bz2
import hashlib

import click
import pytest
import respx
from httpx import Response

from gttrl.updater import Updater, _safe_relative_path, manifest_url, sha1_file

MANIFEST = "https://cdn.toontownrewritten.com/content/patchmanifest.txt"
DOWNLOAD = "https://download.toontownrewritten.com/patches/"


def test_reject_unsafe_paths():
    for path in ("../test", "/root/file", "C:/file", "foo\\bar", "a/../b"):
        with pytest.raises(click.ClickException):
            _safe_relative_path(path)
    with pytest.raises(click.ClickException):
        manifest_url("https://attacker.example/manifest.json")


@pytest.mark.asyncio
@respx.mock
async def test_verified_download_and_repeated_run(tmp_path):
    data = b"this-is-a-valid-game-file" * 100
    digest = hashlib.sha1(data).hexdigest()
    respx.get(MANIFEST).mock(return_value=Response(200, json={
        "test.mf": {"only": ["linux"], "dl": "test.mf.bz2", "hash": digest}
    }))
    download = respx.get(DOWNLOAD + "test.mf.bz2").mock(
        return_value=Response(200, content=bz2.compress(data))
    )
    updater = Updater(tmp_path, "linux")
    assert await updater.update(show_progress=False) == 1
    assert sha1_file(tmp_path / "test.mf") == digest
    assert await updater.update(show_progress=False) == 0
    assert download.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_corrupt_download_preserves_previous_file(tmp_path):
    existing = tmp_path / "phase.mf"
    existing.write_bytes(b"old-game-file")
    expected = hashlib.sha1(b"new-game-file").hexdigest()
    respx.get(MANIFEST).mock(return_value=Response(200, json={
        "phase.mf": {"only": ["linux"], "dl": "phase.mf.bz2", "hash": expected}
    }))
    respx.get(DOWNLOAD + "phase.mf.bz2").mock(
        return_value=Response(200, content=bz2.compress(b"damaged"))
    )
    with pytest.raises(click.ClickException, match="Failed to update"):
        await Updater(tmp_path, "linux").update(show_progress=False)
    assert existing.read_bytes() == b"old-game-file"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["phase.mf"]


@pytest.mark.asyncio
@respx.mock
async def test_concurrency_limited_to_three(tmp_path, monkeypatch):
    digest = hashlib.sha1(b"x").hexdigest()
    manifest = {
        f"{i}.mf": {"only": ["linux"], "dl": f"{i}.bz2", "hash": digest}
        for i in range(7)
    }
    respx.get(MANIFEST).mock(return_value=Response(200, json=manifest))
    active, peak = 0, 0

    async def fake_download(self, client, remote, dest, expected_hash, progress, task):
        nonlocal active, peak
        active += 1
        peak = max(active, peak)
        await asyncio.sleep(0.01)
        active -= 1

    monkeypatch.setattr(Updater, "_download_one", fake_download)
    assert await Updater(tmp_path, "linux", concurrency=3).update(show_progress=False) == 7
    assert peak == 3
