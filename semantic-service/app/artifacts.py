"""Fetching model artifacts for scanning. URLs come from agent tool arguments, i.e. attacker-controlled input,
so downloads are https-only, restricted to allowlisted hosts on every redirect hop (no SSRF into the internal
network), and capped at max_bytes. Paths are confined to the shared artifact volume."""

from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

MAX_REDIRECTS = 5


class ArtifactError(Exception):
    pass


class InvalidSource(ArtifactError):
    pass


class TooLarge(ArtifactError):
    pass


class NotFound(ArtifactError):
    pass


class FetchFailed(ArtifactError):
    pass


def _host_allowed(host: str, allowed: list[str]) -> bool:
    return any(host == h or host.endswith("." + h) for h in allowed)


def _check_url(url: str, allowed: list[str]) -> str:
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise InvalidSource(f"only https URLs are allowed, got {parsed.scheme}")
    if not parsed.hostname or not _host_allowed(parsed.hostname, allowed):
        raise InvalidSource(f"host {parsed.hostname} is not in the artifact allowlist {allowed}")
    return url


async def download(client: httpx.AsyncClient, url: str, allowed: list[str], max_bytes: int) -> tuple[str, bytes]:
    url = _check_url(url, allowed).replace("/blob/", "/resolve/")  # accept HF web links too
    name = urlparse(url).path.rsplit("/", 1)[-1] or "artifact"
    for _ in range(MAX_REDIRECTS + 1):
        async with client.stream("GET", url, follow_redirects=False) as resp:
            if resp.is_redirect:
                url = _check_url(urljoin(url, resp.headers["location"]), allowed)
                continue
            if resp.status_code == 404:
                raise NotFound(f"{url} returned 404")
            if resp.status_code != 200:
                raise FetchFailed(f"{url} returned HTTP {resp.status_code}")
            if int(resp.headers.get("content-length") or 0) > max_bytes:
                raise TooLarge(f"artifact is {resp.headers['content-length']} bytes, limit {max_bytes}")
            chunks, size = [], 0
            async for chunk in resp.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise TooLarge(f"artifact exceeds limit of {max_bytes} bytes")
                chunks.append(chunk)
            return name, b"".join(chunks)
    raise FetchFailed(f"more than {MAX_REDIRECTS} redirects")


def read_path(path: str, root: Path, max_bytes: int) -> tuple[str, bytes]:
    root = root.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise InvalidSource(f"path escapes the artifact volume {root}")
    if not target.is_file():
        raise NotFound(f"{path} not found in {root}")
    if target.stat().st_size > max_bytes:
        raise TooLarge(f"artifact is {target.stat().st_size} bytes, limit {max_bytes}")
    return target.name, target.read_bytes()
