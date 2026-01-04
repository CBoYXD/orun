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


try:  # Prefer real peewee when available for database-heavy tests.
    import peewee as _peewee  # type: ignore
except Exception:  # pragma: no cover - sandbox fallback
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


@pytest.fixture(autouse=True)
def ensure_ddgs_attribute() -> None:
    """Guarantee the tools module always exposes a DDGS attribute for patching."""
    try:
        import orun.tools as _tools  # type: ignore

        if not hasattr(_tools, "DDGS"):
            _tools.DDGS = object  # type: ignore[attr-defined]
    except Exception:
        return


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
"""
Test configuration for orun.

Ensures the project source directory is importable during tests.
"""

import sys
from pathlib import Path
import types


def pytest_configure() -> None:
    """
    Add the project src directory to sys.path for test imports.
    """
    root = Path(__file__).resolve().parents[1]
    src_path = root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    if "ollama" not in sys.modules:
        fake_ollama = types.SimpleNamespace(
            chat=lambda **_kwargs: None, generate=lambda **_kwargs: None
        )
        sys.modules["ollama"] = fake_ollama

    if "peewee" not in sys.modules:
        try:
            import peewee as real_peewee  # type: ignore
        except Exception:  # pragma: no cover - fallback to lightweight stub
            fake_peewee = types.ModuleType("peewee")

            class _Field:
                def __init__(self, *args, **kwargs):
                    pass

                def __call__(self, *args, **kwargs):
                    return self

            class _Model:
                def __init__(self, *args, **kwargs):
                    pass

                def __init_subclass__(cls, **kwargs):
                    return super().__init_subclass__(**kwargs)

            class _SqliteDatabase:
                def __init__(self, *args, **kwargs):
                    pass

                def connect(self, **_kwargs):
                    return None

                def create_tables(self, *args, **kwargs):
                    return None

                def execute_sql(self, *args, **kwargs):
                    return None

            fake_peewee.CharField = _Field
            fake_peewee.DateTimeField = _Field
            fake_peewee.ForeignKeyField = _Field
            fake_peewee.Model = _Model
            fake_peewee.SqliteDatabase = _SqliteDatabase
            fake_peewee.TextField = _Field
            fake_peewee.fn = types.SimpleNamespace()

            sys.modules["peewee"] = fake_peewee
        else:
            sys.modules["peewee"] = real_peewee

    if "rich" not in sys.modules:
        class _RichStub:
            def __init__(self, *args, **kwargs):
                pass

        class _RichConsole:
            def __init__(self, *args, **kwargs):
                self.width = 80
                self.is_terminal = True

            def print(self, *args, **kwargs):
                return None

            def confirm(self, *_args, **_kwargs):
                return True

            def clear(self):
                return None

        rich_console = types.ModuleType("rich.console")
        rich_console.Console = _RichConsole

        rich_align = types.ModuleType("rich.align")
        rich_align.Align = _RichStub

        rich_columns = types.ModuleType("rich.columns")
        rich_columns.Columns = _RichStub

        rich_markdown = types.ModuleType("rich.markdown")
        rich_markdown.Markdown = _RichStub

        rich_panel = types.ModuleType("rich.panel")
        rich_panel.Panel = _RichStub

        rich_progress = types.ModuleType("rich.progress")
        rich_progress.Progress = _RichStub
        rich_progress.SpinnerColumn = _RichStub
        rich_progress.TextColumn = _RichStub
        rich_progress.BarColumn = _RichStub
        rich_progress.TaskProgressColumn = _RichStub

        rich_prompt = types.ModuleType("rich.prompt")
        rich_prompt.Prompt = _RichStub

        rich_syntax = types.ModuleType("rich.syntax")
        rich_syntax.Syntax = _RichStub

        rich_table = types.ModuleType("rich.table")
        rich_table.Table = _RichStub

        rich_text = types.ModuleType("rich.text")
        rich_text.Text = _RichStub

        rich_tree = types.ModuleType("rich.tree")
        rich_tree.Tree = _RichStub

        sys.modules["rich"] = types.ModuleType("rich")
        sys.modules["rich.console"] = rich_console
        sys.modules["rich.align"] = rich_align
        sys.modules["rich.columns"] = rich_columns
        sys.modules["rich.markdown"] = rich_markdown
        sys.modules["rich.panel"] = rich_panel
        sys.modules["rich.progress"] = rich_progress
        sys.modules["rich.prompt"] = rich_prompt
        sys.modules["rich.syntax"] = rich_syntax
        sys.modules["rich.table"] = rich_table
        sys.modules["rich.text"] = rich_text
        sys.modules["rich.tree"] = rich_tree

    if "arxiv" not in sys.modules:
        sys.modules["arxiv"] = types.ModuleType("arxiv")

    if "ddgs" not in sys.modules:
        ddgs_module = types.ModuleType("ddgs")

        class _DDGS:
            def __init__(self, *args, **kwargs):
                pass

        ddgs_module.DDGS = _DDGS
        sys.modules["ddgs"] = ddgs_module

    if "langdetect" not in sys.modules:
        langdetect_module = types.ModuleType("langdetect")

        class LangDetectException(Exception):
            """Stubbed langdetect exception."""

        def detect(_text: str) -> str:
            return "en"

        langdetect_module.detect = detect
        langdetect_module.LangDetectException = LangDetectException
        sys.modules["langdetect"] = langdetect_module

    if "PIL" not in sys.modules:
        pil_module = types.ModuleType("PIL")
        image_module = types.ModuleType("PIL.Image")

        class _Image:
            def __init__(self, *args, **kwargs):
                pass

            @staticmethod
            def open(_path):
                return _Image()

        image_module.Image = _Image
        pil_module.Image = _Image
        sys.modules["PIL"] = pil_module
        sys.modules["PIL.Image"] = image_module
"""Pytest configuration for local imports."""

import sys
from contextlib import nullcontext
from pathlib import Path
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _install_ollama_stub() -> None:
    if "ollama" in sys.modules:
        return

    ollama_stub = types.SimpleNamespace(chat=lambda *a, **k: None, generate=lambda *a, **k: None)
    sys.modules["ollama"] = ollama_stub


def _install_rich_stub() -> None:
    if "rich" in sys.modules:
        return

    class DummyConsole:
        def __init__(self) -> None:
            self.width = 80
            self.is_terminal = True

        def print(self, *args, **kwargs):
            return None

        def confirm(self, _message: str, default: bool = True) -> bool:
            return default

        def clear(self) -> None:
            return None

    class _Simple:
        def __init__(self, *args, **kwargs):
            return

    rich_module = types.ModuleType("rich")
    sys.modules["rich"] = rich_module

    sys.modules["rich.align"] = types.SimpleNamespace(Align=_Simple)
    sys.modules["rich.columns"] = types.SimpleNamespace(Columns=_Simple)
    sys.modules["rich.console"] = types.SimpleNamespace(Console=lambda **kwargs: DummyConsole())
    sys.modules["rich.markdown"] = types.SimpleNamespace(Markdown=_Simple)
    sys.modules["rich.panel"] = types.SimpleNamespace(Panel=_Simple)
    sys.modules["rich.progress"] = types.SimpleNamespace(
        BarColumn=_Simple,
        Progress=_Simple,
        SpinnerColumn=_Simple,
        TaskProgressColumn=_Simple,
        TextColumn=_Simple,
    )
    sys.modules["rich.prompt"] = types.SimpleNamespace(Prompt=types.SimpleNamespace(ask=lambda *a, **k: ""))
    sys.modules["rich.syntax"] = types.SimpleNamespace(Syntax=_Simple)
    sys.modules["rich.table"] = types.SimpleNamespace(Table=_Simple)
    sys.modules["rich.text"] = types.SimpleNamespace(Text=_Simple)
    sys.modules["rich.tree"] = types.SimpleNamespace(Tree=_Simple)


def _install_optional_dependency_stubs() -> None:
    if "ddgs" not in sys.modules:
        sys.modules["ddgs"] = types.SimpleNamespace(DDGS=object)
    if "langdetect" not in sys.modules:
        langdetect = types.SimpleNamespace(
            detect=lambda _text: "en", LangDetectException=Exception
        )
        sys.modules["langdetect"] = langdetect
    if "arxiv" not in sys.modules:
        sys.modules["arxiv"] = types.SimpleNamespace(Search=object)
    if "peewee" not in sys.modules:
        class _Field:
            def __init__(self, *args, **kwargs) -> None:
                return

        class _Model:
            class Meta:
                database = None

            def __init__(self, *args, **kwargs) -> None:
                return

        def _db_factory(*args, **kwargs):
            return types.SimpleNamespace(
                connect=lambda **k: None,
                create_tables=lambda *a, **k: None,
                execute_sql=lambda *a, **k: None,
                close=lambda **k: None,
                connection_context=lambda: nullcontext(),
            )

        peewee = types.SimpleNamespace(
            CharField=_Field,
            DateTimeField=_Field,
            ForeignKeyField=_Field,
            Model=_Model,
            SqliteDatabase=_db_factory,
            TextField=_Field,
            fn=types.SimpleNamespace(),
        )
        sys.modules["peewee"] = peewee
    if "PIL" not in sys.modules:
        pil_module = types.ModuleType("PIL")
        pil_module.Image = type("Image", (), {})  # type: ignore[attr-defined]
        sys.modules["PIL"] = pil_module
        sys.modules["PIL.Image"] = pil_module.Image


_install_ollama_stub()
_install_rich_stub()
_install_optional_dependency_stubs()
# Ensure core module attributes exist for downstream patches.
try:
    import orun.tools as _tools  # type: ignore

    if not hasattr(_tools, "DDGS"):
        _tools.DDGS = object  # type: ignore[attr-defined]
except Exception:
    pass
