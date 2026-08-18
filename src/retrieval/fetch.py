"""Web page fetcher with MD5 file-system cache — Phase 2.

Caches responses in ``data/cache/`` keyed by MD5 hash of the URL.
Returns None on any failure; never raises past this point.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    "(research project; contact: specforge-research)"
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = os.path.join(str(REPO_ROOT), "data", "cache")


def _cache_path(url: str) -> str:
    cache_key = hashlib.md5(url.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{cache_key}.html")


def fetch(url: str, force: bool = False) -> str | None:
    """Fetches and caches a page.

    Args:
        url: The URL to fetch.
        force: If True, re-fetch even if cached.

    Returns:
        Page body as string, or None on any HTTP/network error.
    """
    cache_path = _cache_path(url)

    if not force and os.path.exists(cache_path):
        try:
            return Path(cache_path).read_text(encoding="utf-8")
        except Exception:
            pass

    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
    except requests.RequestException:
        return None

    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        Path(cache_path).write_text(resp.text, encoding="utf-8")
    except Exception:
        pass
    return resp.text


def fetch_multiple(urls: list[str]) -> list[tuple[str, str | None]]:
    """Fetch multiple URLs — returns list of (url, body_or_none)."""
    results: list[tuple[str, str | None]] = []
    for u in urls:
        body = fetch(u)
        results.append((u, body))
    return results
