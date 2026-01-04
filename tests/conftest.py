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
