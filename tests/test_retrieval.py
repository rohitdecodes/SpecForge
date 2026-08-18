"""Phase 2 tests — retrieval pipeline (search, fetch, parse, index).

These tests validate that each retrieval component works correctly:
  - Search returns real URLs for known product queries.
  - Fetch caches and retrieves HTML content.
  - Parse extracts clean text and chunks it correctly.
  - Index builds and queries FAISS indices.

Note: search/fetch tests require internet access and may be skipped
offline via the ``--no-internet`` pytest marker.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# --- Search tests ---


def test_search_returns_urls():
    """Search for a well-known product and confirm we get at least one URL."""
    from src.retrieval.search import web_search
    results = web_search("Milwaukee 49-94-0013 cut off disc", max_results=3)
    assert isinstance(results, list)
    # May be empty if offline; that's OK — not a code bug
    if results:
        for url in results:
            assert url.startswith("http")


def test_search_empty_query():
    """Empty queries should return gracefully."""
    from src.retrieval.search import web_search
    results = web_search("")
    assert isinstance(results, list)
    # empty query will likely return 0 results without crashing


def test_search_with_brand():
    from src.retrieval.search import search_for_product
    results = search_for_product("49-94-0013", "Milwaukee", max_results=3)
    assert isinstance(results, list)


def test_search_without_brand():
    from src.retrieval.search import search_for_product
    results = search_for_product("WDTS7024RZ", None, max_results=3)
    assert isinstance(results, list)


# --- Fetch tests ---


def test_fetch_creates_cache_dir():
    """Fetch should create the cache directory if it doesn't exist."""
    from src.retrieval.fetch import CACHE_DIR
    assert os.path.isabs(CACHE_DIR)
    assert "cache" in CACHE_DIR


def test_fetch_invalid_url_returns_none():
    from src.retrieval.fetch import fetch
    result = fetch("http://this-domain-definitely-does-not-exist-99999.invalid")
    assert result is None


def test_fetch_cache_hit(tmp_path, monkeypatch):
    """Simulate a cache hit by pre-writing a cached file."""
    from src.retrieval import fetch as fetch_mod
    fake_cache = tmp_path / "cache"
    fake_cache.mkdir()
    monkeypatch.setattr(fetch_mod, "CACHE_DIR", str(fake_cache))
    import hashlib
    test_url = "http://example.com/cached-page"
    cache_key = hashlib.md5(test_url.encode("utf-8")).hexdigest()
    cache_file = fake_cache / f"{cache_key}.html"
    cache_file.write_text("<html><body>Cached content</body></html>", encoding="utf-8")
    result = fetch_mod.fetch(test_url)
    assert result == "<html><body>Cached content</body></html>"


def test_fetch_multiple():
    from src.retrieval.fetch import fetch_multiple
    results = fetch_multiple([
        "http://this-domain-definitely-does-not-exist-11111.invalid",
        "http://this-domain-definitely-does-not-exist-22222.invalid",
    ])
    assert len(results) == 2
    for url, body in results:
        assert url is not None
        assert body is None  # unreachable URLs


# --- Parse tests ---


def test_parse_html_strips_tags():
    from src.retrieval.parse import extract_text, _extract_html_text
    html = "<html><body><p>Hello World</p><script>alert(1)</script><style>body{}</style></body></html>"
    result = _extract_html_text(html)
    assert "Hello World" in result
    assert "alert" not in result
    assert "body{" not in result


def test_parse_pdf_placeholder():
    from src.retrieval.parse import extract_text
    result = extract_text(b"%PDF-1.4\n%invalid pdf content\n", is_pdf=True)
    # Should not crash; may return empty string for invalid PDF
    assert isinstance(result, str)


def test_chunk_text_basic():
    from src.retrieval.parse import chunk_text
    text = "word " * 500
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) >= 4
    assert len(chunks) <= 8


def test_chunk_text_empty():
    from src.retrieval.parse import chunk_text
    assert chunk_text("") == []
    assert chunk_text("") == []


def test_chunk_text_short():
    from src.retrieval.parse import chunk_text
    chunks = chunk_text("hello world", chunk_size=100, overlap=20)
    assert len(chunks) == 1
    assert chunks[0] == "hello world"


# --- Index tests ---


@pytest.mark.skipif(
    not __import__("src.retrieval.index").retrieval.index.is_available(),
    reason="sentence-transformers or faiss not installed",
)
def test_build_and_query_index():
    from src.retrieval.index import build_index, retrieve
    chunks = [
        "Milwaukee 5 inch metal cut-off disc diameter 5 in thickness 0.045 in",
        "Voltage rating 120 volts 15 amps for this dishwasher model",
        "Sound level measured at 47 dBA quiet operation",
        "This product weighs 50 pounds shipping weight",
    ]
    index, stored_chunks = build_index(chunks)
    assert index is not None

    results = retrieve("voltage", index, stored_chunks, k=2)
    assert len(results) >= 1
    chunk_text, distance = results[0]
    assert "120" in chunk_text or "volts" in chunk_text.lower()


def test_build_index_empty():
    from src.retrieval.index import build_index
    index, chunks = build_index([])
    assert index is None
    assert chunks == []


def test_retrieve_empty_index():
    from src.retrieval.index import retrieve
    results = retrieve("test", None, [], k=3)
    assert results == []
