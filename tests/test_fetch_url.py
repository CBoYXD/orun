import pathlib
import sys
from types import SimpleNamespace

import pytest

# Ensure the src directory is importable
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.append(str(ROOT / "src"))

from orun import config as orun_config  # noqa: E402
from orun import tools  # noqa: E402


class _DummyResponse:
    """Lightweight response mock for urllib.request.urlopen."""

    def __init__(self, content: str):
        self._content = content.encode("utf-8")
        self.headers = SimpleNamespace(get_content_charset=lambda: "utf-8")

    def read(self) -> bytes:
        return self._content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


@pytest.fixture(autouse=True)
def _mock_cache(monkeypatch):
    """Disable cache writes/reads for fetch_url during tests."""

    monkeypatch.setattr(tools, "get_cached_text", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tools, "set_cached_text", lambda *_args, **_kwargs: None)


def test_fetch_url_blocks_private_ip(monkeypatch):
    monkeypatch.setattr(
        orun_config,
        "get_section",
        lambda name: {
            "fetch_timeout_seconds": 1,
            "fetch_max_chars": 2000,
            "fetch_retry_count": 0,
            "fetch_allow_hosts": [],
            "fetch_block_hosts": ["127.0.0.1"],
            "fetch_block_private_networks": True,
        }
        if name == "limits"
        else {},
    )

    # urlopen should never be called when blocked
    def _fail_urlopen(*_args, **_kwargs):
        raise AssertionError("urlopen should not be invoked for blocked hosts")

    monkeypatch.setattr(tools.urllib.request, "urlopen", _fail_urlopen)

    result = tools.fetch_url("http://127.0.0.1")

    assert "blocked" in result.lower()
    assert "127.0.0.1" in result


def test_fetch_url_rejects_unsupported_scheme(monkeypatch):
    monkeypatch.setattr(
        orun_config,
        "get_section",
        lambda name: tools.orun_config.get_section(name),
    )

    result = tools.fetch_url("ftp://example.com/resource")

    assert "unsupported url scheme" in result.lower()


def test_fetch_url_allows_public_host(monkeypatch):
    monkeypatch.setattr(
        orun_config,
        "get_section",
        lambda name: {
            "fetch_timeout_seconds": 1,
            "fetch_max_chars": 5000,
            "fetch_retry_count": 0,
            "fetch_allow_hosts": [],
            "fetch_block_hosts": [],
            "fetch_block_private_networks": True,
        }
        if name == "limits"
        else {},
    )

    monkeypatch.setattr(
        tools.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (tools.socket.AF_INET, None, None, None, ("93.184.216.34", 0)),
        ],
    )

    dummy_content = "Example content from public host. " * 3
    monkeypatch.setattr(
        tools.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _DummyResponse(dummy_content),
    )

    result = tools.fetch_url("example.com")

    assert "Example content from public host" in result
    assert "Source: https://example.com" in result
