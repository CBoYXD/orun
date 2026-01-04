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
import pathlib
import sys
import types

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"


def _install_rich_stub() -> None:
    """Install minimal Rich stubs so imports succeed without the dependency."""
    if "rich" in sys.modules:
        return

    def _dummy_print(*args, **kwargs):
        return None

    class _Console:
        def __init__(self, *args, **kwargs):
            self.is_terminal = True
            self.width = 80

        def print(self, *args, **kwargs):
            _dummy_print(*args, **kwargs)

        def clear(self):
            return None

    def _make_module(name: str):
        module = types.ModuleType(name)
        sys.modules[name] = module
        return module

    rich_module = _make_module("rich")
    align_module = _make_module("rich.align")
    columns_module = _make_module("rich.columns")
    console_module = _make_module("rich.console")
    markdown_module = _make_module("rich.markdown")
    panel_module = _make_module("rich.panel")
    progress_module = _make_module("rich.progress")
    prompt_module = _make_module("rich.prompt")
    syntax_module = _make_module("rich.syntax")
    table_module = _make_module("rich.table")
    text_module = _make_module("rich.text")
    tree_module = _make_module("rich.tree")

    class _Stub:
        def __init__(self, *args, **kwargs):
            pass

    # Populate modules with minimal classes
    align_module.Align = _Stub
    columns_module.Columns = _Stub
    console_module.Console = _Console
    markdown_module.Markdown = _Stub
    panel_module.Panel = _Stub
    progress_module.BarColumn = _Stub
    progress_module.Progress = _Stub
    progress_module.SpinnerColumn = _Stub
    progress_module.TaskProgressColumn = _Stub
    progress_module.TextColumn = _Stub
    prompt_module.Prompt = _Stub
    syntax_module.Syntax = _Stub
    table_module.Table = _Stub
    text_module.Text = _Stub
    tree_module.Tree = _Stub

    # Reference submodules from root for completeness
    rich_module.align = align_module
    rich_module.columns = columns_module
    rich_module.console = console_module
    rich_module.markdown = markdown_module
    rich_module.panel = panel_module
    rich_module.progress = progress_module
    rich_module.prompt = prompt_module
    rich_module.syntax = syntax_module
    rich_module.table = table_module
    rich_module.text = text_module
    rich_module.tree = tree_module


def _install_dependency_stubs() -> None:
    """Stub optional third-party modules used by orun during tests."""
    if "arxiv" not in sys.modules:
        arxiv_module = types.ModuleType("arxiv")

        class _Search:
            def __init__(self, *args, **kwargs):
                pass

            def results(self):
                return []

        arxiv_module.Search = _Search
        sys.modules["arxiv"] = arxiv_module

    if "ddgs" not in sys.modules:
        ddgs_module = types.ModuleType("ddgs")
        ddgs_module.DDGS = lambda *args, **kwargs: None
        sys.modules["ddgs"] = ddgs_module

    if "langdetect" not in sys.modules:
        langdetect_module = types.ModuleType("langdetect")

        def _detect(text):
            return "en"

        class _LangDetectException(Exception):
            pass

        langdetect_module.detect = _detect
        langdetect_module.LangDetectException = _LangDetectException
        sys.modules["langdetect"] = langdetect_module

    if "PIL" not in sys.modules:
        pil_module = types.ModuleType("PIL")
        image_module = types.ModuleType("PIL.Image")
        imagegrab_module = types.ModuleType("PIL.ImageGrab")

        class _Image:
            pass

        image_module.Image = _Image
        imagegrab_module.ImageGrab = None
        pil_module.Image = _Image
        pil_module.ImageGrab = None

        sys.modules["PIL"] = pil_module
        sys.modules["PIL.Image"] = image_module
        sys.modules["PIL.ImageGrab"] = imagegrab_module

    if "ollama" not in sys.modules:
        ollama_module = types.ModuleType("ollama")

        def _list():
            return {"models": []}

        def _chat(*args, **kwargs):
            raise RuntimeError("Ollama not available in test environment")

        ollama_module.list = _list
        ollama_module.chat = _chat
        sys.modules["ollama"] = ollama_module


_install_rich_stub()
_install_dependency_stubs()

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from orun import config as orun_config, tools, utils  # noqa: E402


def _limits_with_timeout(timeout_seconds: float) -> dict:
    return {"shell_timeout_seconds": timeout_seconds, "shell_output_limit": 12000}


def test_run_shell_command_allowed_with_allowlist(monkeypatch):
    def fake_get_section(name: str):
        if name == "shell":
            return {"allowlist": ["echo"], "denylist": []}
        if name == "limits":
            return _limits_with_timeout(5)
        return {}

    monkeypatch.setattr(orun_config, "get_section", fake_get_section)

    result = tools.run_shell_command("echo hello")
    assert "hello" in result


def test_run_shell_command_blocked_by_allowlist(monkeypatch):
    def fake_get_section(name: str):
        if name == "shell":
            return {"allowlist": ["echo"], "denylist": []}
        if name == "limits":
            return _limits_with_timeout(5)
        return {}

    monkeypatch.setattr(orun_config, "get_section", fake_get_section)

    result = tools.run_shell_command("ls")
    assert "allowlist" in result


def test_run_shell_command_blocked_by_sandbox(monkeypatch):
    def fake_get_section(name: str):
        if name == "shell":
            return {"allowlist": [], "denylist": []}
        if name == "limits":
            return _limits_with_timeout(5)
        return {}

    monkeypatch.setattr(orun_config, "get_section", fake_get_section)
    monkeypatch.setattr(
        utils,
        "is_path_allowed",
        lambda path: (False, "Path blocked") if path == "/tmp" else (True, ""),
    )

    result = tools.run_shell_command("cd /tmp && ls")
    assert "Path blocked" in result


def test_run_shell_command_times_out(monkeypatch):
    def fake_get_section(name: str):
        if name == "shell":
            return {"allowlist": [], "denylist": []}
        if name == "limits":
            return _limits_with_timeout(0.1)
        return {}

    monkeypatch.setattr(orun_config, "get_section", fake_get_section)

    result = tools.run_shell_command(
        'python -c "import time; time.sleep(2)"'  # Exceeds timeout
    )
    assert "timed out" in result
