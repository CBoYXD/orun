from types import SimpleNamespace

from orun import config as orun_config, tools


def test_fetch_url_returns_cached(monkeypatch):
    monkeypatch.setattr(tools, "get_cached_text", lambda key: "cached response")
    monkeypatch.setattr(tools.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network called")))

    result = tools.fetch_url("example.com")

    assert result == "cached response"


def test_fetch_url_respects_timeout_and_falls_back(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        url = getattr(request, "full_url", request)
        calls.append({"url": url, "timeout": timeout})
        if "r.jina.ai" in url:
            raise TimeoutError("timeout")

        html = b"<html><title>Example</title><body><p>Hello</p></body></html>"

        class Response:
            def __init__(self, body: bytes):
                self._body = body
                self.headers = SimpleNamespace(get_content_charset=lambda: None)

            def read(self) -> bytes:
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

        return Response(html)

    monkeypatch.setattr(tools.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(tools.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        orun_config,
        "get_section",
        lambda name: {
            "fetch_timeout_seconds": 3,
            "fetch_max_chars": 5000,
            "fetch_retry_count": 0,
        }
        if name == "limits"
        else {},
    )

    cached = {}
    monkeypatch.setattr(tools, "set_cached_text", lambda key, value: cached.setdefault("value", value))

    result = tools.fetch_url("https://example.com")

    assert "Example" in result
    assert "Hello" in result
    assert result.endswith("Source: https://example.com")
    assert cached["value"] == result
    assert [call["timeout"] for call in calls] == [3, 3]
