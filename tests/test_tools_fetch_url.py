"""Tests for the fetch_url helper."""

from __future__ import annotations

import io
import urllib.request
from http.client import HTTPMessage

import pytest

from orun import config as orun_config
from orun import tools


class FakeResponse:
    """Simple response wrapper for urlopen stubbing."""

    def __init__(self, body: bytes, headers: HTTPMessage | None = None):
        self._buffer = io.BytesIO(body)
        self.headers = headers or HTTPMessage()

    def read(self, size: int | None = -1) -> bytes:  # pragma: no cover - passthrough
        return self._buffer.read(size)

    def __enter__(self):  # pragma: no cover - passthrough
        return self

    def __exit__(self, exc_type, exc, tb):  # pragma: no cover - passthrough
        return False


def _build_headers(content_length: int | None = None, charset: str = "utf-8") -> HTTPMessage:
    headers = HTTPMessage()
    headers.add_header("Content-Type", f"text/plain; charset={charset}")
    if content_length is not None:
        headers.add_header("Content-Length", str(content_length))
    return headers


def test_rejects_non_http_scheme(monkeypatch):
    result = tools.fetch_url("ftp://example.com")
    assert "Only http and https" in result


def test_rejects_private_ip(monkeypatch):
    result = tools.fetch_url("http://127.0.0.1")
    assert "blocked" in result.lower()


def test_allows_public_host_and_caches_on_success(monkeypatch):
    responses: list[FakeResponse] = []

    def fake_urlopen(request, timeout=0):
        method = request.get_method() if isinstance(request, urllib.request.Request) else "GET"
        if method == "HEAD":
            headers = _build_headers(content_length=200)
            resp = FakeResponse(b"", headers=headers)
            responses.append(resp)
            return resp

        headers = _build_headers(content_length=200)
        body = b"#" * 200  # large enough to avoid short-content path
        resp = FakeResponse(body, headers=headers)
        responses.append(resp)
        return resp

    cache: dict[str, str] = {}

    monkeypatch.setattr(tools.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(tools, "get_cached_text", lambda key: cache.get(key))
    monkeypatch.setattr(tools, "set_cached_text", lambda key, value: cache.setdefault(key, value))
    monkeypatch.setattr(
        orun_config,
        "get_section",
        lambda name: {
            "fetch_timeout_seconds": 5,
            "fetch_max_chars": 15000,
            "fetch_retry_count": 0,
        },
    )

    result = tools.fetch_url("https://example.com")

    assert "Source: https://example.com" in result
    assert cache  # ensured caching occurred
    assert any(resp.headers.get("Content-Length") for resp in responses)


def test_blocks_oversized_responses_via_head(monkeypatch):
    def fake_urlopen(request, timeout=0):
        headers = _build_headers(content_length=10_000)
        return FakeResponse(b"", headers=headers)

    monkeypatch.setattr(tools.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        orun_config,
        "get_section",
        lambda name: {
            "fetch_timeout_seconds": 5,
            "fetch_max_chars": 100,
            "fetch_retry_count": 0,
        },
    )

    result = tools.fetch_url("https://example.com")

    assert "too large" in result.lower() or "exceeded" in result.lower()


def test_blocks_oversized_stream_without_length(monkeypatch):
    body = b"x" * 500

    def fake_urlopen(request, timeout=0):
        headers = _build_headers(content_length=None)
        return FakeResponse(body, headers=headers)

    monkeypatch.setattr(tools.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        orun_config,
        "get_section",
        lambda name: {
            "fetch_timeout_seconds": 5,
            "fetch_max_chars": 100,
            "fetch_retry_count": 0,
        },
    )

    result = tools.fetch_url("https://example.com")

    assert "exceeded maximum" in result.lower()
