"""Asynchronous, verified and interruption-safe game patch downloads."""

from __future__ import annotations

import asyncio
import bz2
import hashlib
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urljoin, urlsplit

import aiofiles
import click
import httpx
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TransferSpeedColumn,
)

from .constants import DEFAULT_PATCH_MANIFEST

DOWNLOAD_BASE = "https://download.toontownrewritten.com/patches/"
CDN_BASE = "https://cdn.toontownrewritten.com"
SHA1_PATTERN = re.compile(r"[0-9a-fA-F]{40}\Z")


def _safe_relative_path(value: str) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or ":" in value
        or value.startswith("/")
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise click.ClickException(f"Unsafe filename in patch manifest: {value!r}")
    return Path(*PurePosixPath(value).parts)


def _safe_destination(game_dir: Path, name: str) -> Path:
    root = game_dir.resolve()
    destination = game_dir / _safe_relative_path(name)
    if not destination.resolve().is_relative_to(root):
        raise click.ClickException(f"Patch destination escapes the game directory: {name!r}")
    return destination


def manifest_url(manifest: str | None) -> str:
    if not manifest:
        return DEFAULT_PATCH_MANIFEST
    # The login API returns a path, not an arbitrary download server.
    if not isinstance(manifest, str):
        raise click.ClickException("Invalid patch manifest path")
    url = urljoin(CDN_BASE, manifest)
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.netloc != "cdn.toontownrewritten.com"
        or not parts.path.startswith("/content/")
        or parts.query
        or parts.fragment
    ):
        raise click.ClickException("TTR provided an unsupported manifest URL")
    return url


def sha1_file(path: Path) -> str:
    checksum = hashlib.sha1()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def _unpack_and_verify(compressed: Path, output: Path, expected_hash: str) -> None:
    digest = hashlib.sha1()
    # BZ2File bounds uncompressed memory use; a single bz2.decompress(chunk)
    # can expand into a very large buffer.
    with bz2.open(compressed, "rb") as source, output.open("wb") as dest:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            dest.write(chunk)
            digest.update(chunk)
    if digest.hexdigest().lower() != expected_hash.lower():
        raise ValueError("Downloaded file SHA-1 does not match the patch manifest")


class Updater:
    def __init__(self, game_dir: Path, host_os: str, *, concurrency: int = 3):
        if not 1 <= concurrency <= 16:
            raise ValueError("concurrency must be between 1 and 16")
        self.game_dir = Path(game_dir).expanduser()
        self.host_os = host_os
        self.concurrency = concurrency

    async def update(self, manifest: str | None = None, *, show_progress: bool = True) -> int:
        self.game_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10), follow_redirects=True) as client:
            response = await client.get(manifest_url(manifest))
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise click.ClickException("Invalid TTR patch manifest")
            downloads = []
            for name, info in payload.items():
                if not isinstance(info, dict):
                    raise click.ClickException(f"Invalid manifest entry: {name}")
                targets = info.get("only")
                if not isinstance(targets, list) or not all(
                    isinstance(target, str) for target in targets
                ):
                    raise click.ClickException(f"Invalid OS targets for {name}")
                if self.host_os not in targets:
                    continue
                path = _safe_destination(self.game_dir, name)
                encoded_name = info.get("dl")
                if not isinstance(encoded_name, str):
                    raise click.ClickException(f"Invalid download filename for {name}")
                # The TTR manifest already URL-encodes names with spaces.
                # Decode once, validate the result, then quote exactly once
                # when constructing the patch URL.
                remote = str(_safe_relative_path(unquote(encoded_name)))
                expected = info.get("hash")
                if not isinstance(expected, str) or not SHA1_PATTERN.fullmatch(expected):
                    raise click.ClickException(f"Invalid SHA-1 for {name}")
                if not path.is_file() or await asyncio.to_thread(sha1_file, path) != expected.lower():
                    downloads.append((name, remote, path, expected))
            if not downloads:
                click.echo("Game files are already up to date.")
                return 0
            click.echo(f"Updating {len(downloads)} game file(s), {self.concurrency} at a time.")
            semaphore = asyncio.Semaphore(self.concurrency)
            progress = Progress(
                TextColumn("{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                transient=True,
                disable=not show_progress,
            )
            with progress:
                async def worker(name: str, remote: str, path: Path, digest: str):
                    async with semaphore:
                        task = progress.add_task(name, total=None)
                        try:
                            await self._download_one(client, remote, path, digest, progress, task)
                        finally:
                            progress.remove_task(task)
                await asyncio.gather(*(worker(*item) for item in downloads))
            return len(downloads)

    async def _download_one(
        self,
        client: httpx.AsyncClient,
        remote: str,
        destination: Path,
        expected_hash: str,
        progress: Progress,
        task: int,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        url = DOWNLOAD_BASE + "/".join(quote(segment) for segment in remote.split("/"))
        last_error: Exception | None = None
        for attempt in range(3):
            compressed: Path | None = None
            unpacked: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as fp:
                    compressed = Path(fp.name)
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as fp:
                    unpacked = Path(fp.name)
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    total = int(response.headers.get("content-length", "0"))
                    progress.update(task, total=total or None, completed=0)
                    async with aiofiles.open(compressed, "wb") as output:
                        async for chunk in response.aiter_bytes(128 * 1024):
                            await output.write(chunk)
                            progress.advance(task, len(chunk))
                await asyncio.to_thread(_unpack_and_verify, compressed, unpacked, expected_hash)
                os.replace(unpacked, destination)
                return
            except (httpx.HTTPError, OSError, EOFError, ValueError) as error:
                last_error = error
                if attempt < 2:
                    await asyncio.sleep(min(2 ** attempt, 5))
            finally:
                for temporary in (compressed, unpacked):
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
        raise click.ClickException(f"Failed to update {destination.name}: {last_error}")
