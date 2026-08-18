"""Web search — Phase 2 retrieval.

Zero-cost DuckDuckGo search.  Primary backend is the `duckduckgo_search`
package (DDGS) which talks to DuckDuckGo's backend API; falls back to the
DuckDuckGo HTML endpoint (which may be CAPTCHA-gated).  Returns candidate
URLs ranked by relevance (no API key required).
"""
from __future__ import annotations

import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    "(research project; contact: specforge-research)"
)


def _search_ddgs(query: str, max_results: int) -> list[str]:
    """Search via the duckduckgo_search package (backend API)."""
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        urls = [r.get("href", "") for r in results if r.get("href")]
        return [u for u in urls if u.startswith("http")][:max_results]
    except Exception:
        return []


def _search_html(query: str, max_results: int) -> list[str]:
    """Search DuckDuckGo HTML endpoint — returns list of result URLs."""
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = soup.select("a.result__a")

    urls: list[str] = []
    for link in results:
        href = link.get("href", "")
        if href.startswith("//"):
            href = "https:" + href
        # DuckDuckGo HTML endpoint wraps URLs via a redirect — extract target
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        actual = qs.get("uddg", [href])[0]
        if actual.startswith("http") and not actual.startswith(
            ("https://duckduckgo.com", "https://html.duckduckgo.com")
        ):
            urls.append(actual)
            if len(urls) >= max_results:
                break

    return urls[:max_results]


def web_search(query: str, max_results: int = 5) -> list[str]:
    """Search DuckDuckGo — returns list of result URLs.

    Tries the `duckduckgo_search` package first, then the HTML endpoint.

    Args:
        query: The search query string.
        max_results: Maximum number of URLs to return (default 5).

    Returns:
        List of URL strings.  Empty list on failure or no results.
    """
    urls = _search_ddgs(query, max_results)
    if urls:
        return urls
    return _search_html(query, max_results)


def search_for_product(
    part_number: str, brand: str | None = None, max_results: int = 5
) -> list[str]:
    """Convenience: builds a search query and returns URLs."""
    if brand:
        query = f"{part_number} {brand} specifications"
    else:
        query = f"{part_number} specifications"
    # brief delay to be respectful
    time.sleep(1.0)
    return web_search(query, max_results)
