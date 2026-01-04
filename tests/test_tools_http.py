from __future__ import annotations

import json
import sys
import tempfile
import types
from email.message import Message
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

if "arxiv" not in sys.modules:
    sys.modules["arxiv"] = types.ModuleType("arxiv")

if "ddgs" not in sys.modules:
    ddgs_module = types.ModuleType("ddgs")
    ddgs_module.DDGS = lambda *args, **kwargs: None
    sys.modules["ddgs"] = ddgs_module

if "langdetect" not in sys.modules:
    langdetect_module = types.ModuleType("langdetect")

    class _DummyLangDetectException(Exception):
        ...

    langdetect_module.detect = lambda text: "en"
    langdetect_module.LangDetectException = _DummyLangDetectException
    sys.modules["langdetect"] = langdetect_module

if "ollama" not in sys.modules:
    ollama_module = types.ModuleType("ollama")
    ollama_module.list = lambda: []
    sys.modules["ollama"] = ollama_module

if "PIL" not in sys.modules:
    pil_package = types.ModuleType("PIL")
    pil_package.__path__ = []
    sys.modules["PIL"] = pil_package

if "PIL.Image" not in sys.modules:
    image_module = types.ModuleType("PIL.Image")

    class _StubImage:
        mode = "RGB"
        size = (0, 0)

        def save(self, *args, **kwargs):
            return None

        def convert(self, *args, **kwargs):
            return self

    image_module.Image = _StubImage
    image_module.open = lambda *args, **kwargs: _StubImage()
    image_module.new = lambda *args, **kwargs: _StubImage()
    sys.modules["PIL.Image"] = image_module

if "PIL.ImageGrab" not in sys.modules:
    sys.modules["PIL.ImageGrab"] = types.ModuleType("PIL.ImageGrab")

if "orun.rich_utils" not in sys.modules:
    rich_utils_module = types.ModuleType("orun.rich_utils")

    class _StubColors:
        RED = "red"
        GREEN = "green"
        YELLOW = "yellow"
        CYAN = "cyan"
        GREY = "grey"
        DIM = "dim"

    class _StubConsole:
        def print(self, *args, **kwargs):
            return ""

        def input(self, *args, **kwargs):
            return ""

    def _noop(*args, **kwargs):
        return ""

    rich_utils_module.console = _StubConsole()
    rich_utils_module.Colors = _StubColors
    rich_utils_module.print_error = _noop
    rich_utils_module.print_success = _noop
    rich_utils_module.print_warning = _noop
    rich_utils_module.print_info = _noop
    sys.modules["orun.rich_utils"] = rich_utils_module

if "rich" not in sys.modules:
    rich_package = types.ModuleType("rich")
    rich_package.__path__ = []
    sys.modules["rich"] = rich_package

_RICH_STUBS = {
    "rich.align": ("Align",),
    "rich.box": ("Box",),
    "rich.columns": ("Columns",),
    "rich.panel": ("Panel",),
    "rich.syntax": ("Syntax",),
    "rich.table": ("Table",),
    "rich.text": ("Text",),
    "rich.theme": ("Theme",),
}

for module_name, attributes in _RICH_STUBS.items():
    if module_name not in sys.modules:
        module = types.ModuleType(module_name)
        for attr in attributes:
            setattr(module, attr, type(attr, (), {}) )
        sys.modules[module_name] = module

if "rich.console" not in sys.modules:
    console_module = types.ModuleType("rich.console")

    class _Console:
        def __init__(self, *args, **kwargs):
            ...

        def print(self, *args, **kwargs):
            return ""

        def input(self, *args, **kwargs):
            return ""

    console_module.Console = _Console
    sys.modules["rich.console"] = console_module

from orun import tools  # noqa: E402
from orun.http_client import HttpResponse  # noqa: E402


class StubHttpClient:
    def __init__(self, responses: list[HttpResponse | Exception]):
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url: str, headers=None) -> HttpResponse:
        self.calls.append(url)
        outcome = self.responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ToolsHttpTests(TestCase):
    def test_fetch_url_cache_hit_and_miss(self) -> None:
        html_body = b"<html><body><h1>Title</h1><p>Hello world</p></body></html>"
        response = HttpResponse(
            url="https://example.com",
            status=200,
            body=html_body,
            headers=Message(),
        )
        client = StubHttpClient([response])

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "orun.cache._cache_dir", return_value=Path(tmpdir)
        ):
            first = tools.fetch_url("https://example.com", http_client=client)
            payload = json.loads(first)
            self.assertTrue(payload["success"])
            self.assertIn("Hello world", payload["data"])
            self.assertEqual(len(client.calls), 1)
            self.assertIn("r.jina.ai", client.calls[0])

            cached = tools.fetch_url("https://example.com", http_client=client)
            self.assertEqual(payload, json.loads(cached))
            self.assertEqual(len(client.calls), 1)

    def test_web_search_google_malformed_response(self) -> None:
        message = Message()
        malformed_response = HttpResponse(
            url="https://googleapis.com",
            status=200,
            body=b"not-json",
            headers=message,
        )
        client = StubHttpClient([malformed_response])

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "orun.cache._cache_dir", return_value=Path(tmpdir)
        ), patch.object(
            tools.search_config, "has_google_credentials", return_value=True
        ), patch.object(
            tools.search_config, "google_api_key", "key"
        ), patch.object(
            tools.search_config, "google_cse_id", "cse"
        ), patch(
            "orun.tools.DDGS", side_effect=RuntimeError("ddg disabled")
        ):
            result = tools.web_search("test query", http_client=client)
            payload = json.loads(result)
            self.assertFalse(payload["success"])
            self.assertIn("Malformed search response", payload["error"])

    def test_web_search_cache_hit(self) -> None:
        message = Message()
        body = json.dumps(
            {"items": [{"title": "Hello", "link": "https://example.com", "snippet": "Snippet"}]}
        ).encode()
        response = HttpResponse(
            url="https://googleapis.com",
            status=200,
            body=body,
            headers=message,
        )
        client = StubHttpClient([response])

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "orun.cache._cache_dir", return_value=Path(tmpdir)
        ), patch.object(
            tools.search_config, "has_google_credentials", return_value=True
        ), patch.object(
            tools.search_config, "google_api_key", "key"
        ), patch.object(
            tools.search_config, "google_cse_id", "cse"
        ):
            first = tools.web_search("hello world", http_client=client)
            payload = json.loads(first)
            self.assertTrue(payload["success"])
            self.assertEqual(len(payload["data"]), 1)

            cached = tools.web_search("hello world", http_client=client)
            self.assertEqual(json.loads(cached), payload)
            self.assertEqual(len(client.calls), 1)
            self.assertIn("googleapis", client.calls[0])
