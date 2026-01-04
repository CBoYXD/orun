import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _install_stub(name: str, attrs: dict[str, Any] | None = None) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in (attrs or {}).items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


# Stub external dependencies that may not be installed in the CI sandbox.
class _DummyConsole:
    def __init__(self, *_args, **_kwargs):
        self.width = 80
        self.is_terminal = True

    def print(self, *_args, **_kwargs):
        return None

    def confirm(self, _message, default=True):
        return default

    def clear(self):
        return None


_install_stub(
    "rich.console",
    {"Console": _DummyConsole},
)
_install_stub("rich.align", {"Align": object})
_install_stub("rich.columns", {"Columns": list})
_install_stub("rich.markdown", {"Markdown": lambda content: content})
_install_stub("rich.panel", {"Panel": object})
_install_stub(
    "rich.progress",
    {
        "BarColumn": object,
        "Progress": type("Progress", (), {"__init__": lambda self, *a, **k: None}),
        "SpinnerColumn": object,
        "TaskProgressColumn": object,
        "TextColumn": object,
    },
)
_install_stub("rich.prompt", {"Prompt": type("Prompt", (), {"ask": staticmethod(lambda *a, **k: "")})})
_install_stub("rich.syntax", {"Syntax": object})
_install_stub("rich.table", {"Table": type("Table", (), {"__init__": lambda self, *a, **k: None, "add_column": lambda *a, **k: None})})
_install_stub("rich.text", {"Text": str})
_install_stub("rich.tree", {"Tree": type("Tree", (), {"__init__": lambda self, *a, **k: None})})
_install_stub("rich", {})

def _work_stub(fn=None, **_kwargs):
    if fn is not None:
        return fn

    def decorator(inner_fn):
        return inner_fn

    return decorator


textual_work_module = _install_stub("textual.work", {"work": _work_stub})
_install_stub(
    "textual.app",
    {
        "App": type("App", (), {"__init__": lambda self, *a, **k: None, "run": lambda self: None}),
        "ComposeResult": list,
    },
)
_install_stub(
    "textual.binding",
    {"Binding": type("Binding", (), {"__init__": lambda self, *a, **k: None})},
)
_install_stub("textual.containers", {"VerticalScroll": list})
_install_stub(
    "textual.widgets",
    {
        "Footer": object,
        "Header": object,
        "Input": type(
            "Input",
            (),
            {
                "__init__": lambda self, *a, **k: None,
                "Changed": type("Changed", (), {}),
                "Submitted": type("Submitted", (), {}),
            },
        ),
        "Static": type("Static", (), {"__init__": lambda self, *a, **k: None}),
    },
)
_install_stub("textual.screen", {"Screen": object})
textual_module = _install_stub("textual", {})
setattr(textual_module, "work", textual_work_module.work)

_install_stub("ddgs", {"DDGS": type("DDGS", (), {"text": lambda *a, **k: []})})
_install_stub(
    "langdetect",
    {
        "detect": lambda _text: "en",
        "LangDetectException": Exception,
    },
)

pil_module = _install_stub("PIL", {})
pil_module.Image = type("Image", (), {})
pil_module.ImageGrab = None

_install_stub("arxiv", {"Search": lambda *a, **k: []})


class _DummyDatabase:
    def __init__(self, *args, **kwargs):
        pass

    def connect(self, **kwargs):
        return None

    def create_tables(self, *args, **kwargs):
        return None

    def execute_sql(self, *args, **kwargs):
        return None

    def __getattr__(self, _name):
        return lambda *a, **k: None


class _DummyFn:
    def __getattr__(self, _name):
        return lambda *a, **k: 0


_install_stub(
    "peewee",
    {
        "Model": type("Model", (), {}),
        "CharField": type("CharField", (), {"__init__": lambda self, *a, **k: None}),
        "DateTimeField": type("DateTimeField", (), {"__init__": lambda self, *a, **k: None}),
        "ForeignKeyField": type("ForeignKeyField", (), {"__init__": lambda self, *a, **k: None}),
        "SqliteDatabase": _DummyDatabase,
        "TextField": type("TextField", (), {"__init__": lambda self, *a, **k: None}),
        "fn": _DummyFn(),
    },
)

_install_stub(
    "ollama",
    {
        "chat": lambda **kwargs: {},
        "list": lambda: {"models": []},
    },
)

from orun import config as orun_config, db


def pytest_addoption(parser):
    """Accept coverage flags even if pytest-cov is unavailable in the sandbox."""
    parser.addoption("--cov", action="append", default=[], help="Dummy coverage flag")
    parser.addoption(
        "--cov-report", action="append", default=[], help="Dummy coverage report flag"
    )


@pytest.fixture(autouse=True)
def isolate_home(monkeypatch, tmp_path: Path) -> Path:
    """Redirect Path.home() to a temporary directory for all tests."""
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setenv("ORUN_CONFIG_PATH", str(fake_home / ".orun" / "config.json"))
    return fake_home


@pytest.fixture(autouse=True)
def preload_default_config(isolate_home: Path) -> None:
    """Persist a minimal config file so code paths relying on disk config stay happy."""
    config_path = Path(isolate_home) / ".orun" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({}), encoding="utf-8")


@pytest.fixture()
def in_memory_db(monkeypatch) -> dict[str, Any]:
    """Stub the DB layer with in-memory stores to avoid touching SQLite."""
    conversations: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []

    def create_conversation(model: str) -> int:
        conv_id = len(conversations) + 1
        conversations.append({"id": conv_id, "model": model})
        return conv_id

    def add_message(conversation_id: int, role: str, content: str, images=None) -> None:
        messages.append(
            {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "images": images,
            }
        )

    monkeypatch.setattr(db, "create_conversation", create_conversation)
    monkeypatch.setattr(db, "add_message", add_message)
    monkeypatch.setattr(db, "initialize", lambda: None)

    return {"conversations": conversations, "messages": messages}


@pytest.fixture()
def stub_ollama(monkeypatch) -> SimpleNamespace:
    """Provide a mutable ollama stub that tests can customize."""
    stub = SimpleNamespace(
        chat=lambda **kwargs: {},
        list=lambda: {"models": []},
    )
    monkeypatch.setattr("orun.core.ollama", stub)
    monkeypatch.setattr("orun.utils.ollama", stub)
    return stub


@pytest.fixture()
def stub_config(monkeypatch) -> Callable[[dict[str, Any]], None]:
    """Allow tests to override config sections easily."""

    def _apply(overrides: dict[str, Any]) -> None:
        def get_section(name: str) -> dict[str, Any]:
            base = orun_config.DEFAULTS.get(name, {}).copy()
            base.update(overrides.get(name, {}))
            return base

        monkeypatch.setattr(orun_config, "get_section", get_section)

    return _apply
