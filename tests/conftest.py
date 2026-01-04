"""Pytest configuration for local imports."""

import sys
from contextlib import nullcontext
from pathlib import Path
import types

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

# Disable persistent caching during tests to avoid cross-run pollution.
try:
    import orun.cache as _cache  # type: ignore

    _cache.get_cached_text = lambda key: None
    _cache.set_cached_text = lambda key, value: None
except Exception:
    pass
