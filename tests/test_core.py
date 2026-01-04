import json
from types import SimpleNamespace

from orun import core, tools, utils


def test_run_single_shot_invokes_tools_and_streams(monkeypatch, in_memory_db, stub_ollama):
    tool_invocations = []

    def fake_fetch_url(url: str) -> str:
        tool_invocations.append(url)
        return "fetched content"

    monkeypatch.setitem(tools.AVAILABLE_TOOLS, "fetch_url", fake_fetch_url)
    monkeypatch.setattr(tools, "get_tools_for_model", lambda model: [{"name": "fetch_url"}])
    monkeypatch.setattr(utils, "ensure_ollama_running", lambda: None)
    monkeypatch.setattr(core.console, "input", lambda *_args, **_kwargs: "y", raising=False)

    stream_content = "Assistant final reply"

    def fake_chat(**kwargs):
        if kwargs.get("stream"):
            def generator():
                yield {"message": {"content": stream_content}}

            return generator()

        tool_call = SimpleNamespace(
            function=SimpleNamespace(
                name="fetch_url",
                arguments=json.dumps({"url": "https://example.com"}),
            )
        )
        return {"message": {"content": "", "tool_calls": [tool_call]}}

    stub_ollama.chat = fake_chat

    result = core.run_single_shot(
        model_name="test-model",
        user_prompt="test prompt",
        image_paths=None,
        use_tools=True,
        quiet=True,
    )

    assert result == stream_content
    assert tool_invocations == ["https://example.com"]
    assert in_memory_db["conversations"][0]["model"] == "test-model"
import sys
import types
from pathlib import Path
from types import ModuleType
from unittest import mock

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))


def _install_rich_stubs() -> None:
    """Install minimal stub modules for `rich` to satisfy imports in tests."""

    class _Dummy:
        def __init__(self, *_, **__):
            pass

    class _DummyConsole:
        def __init__(self, *_, **__):
            self.width = 80
            self.is_terminal = True

        def print(self, *_, **__):
            return None

        def input(self, *_, **__):
            return ""

        def confirm(self, *_, **__):
            return False

        def clear(self):
            return None

    stubs = {
        "rich": ModuleType("rich"),
        "rich.align": ModuleType("rich.align"),
        "rich.columns": ModuleType("rich.columns"),
        "rich.console": ModuleType("rich.console"),
        "rich.markdown": ModuleType("rich.markdown"),
        "rich.panel": ModuleType("rich.panel"),
        "rich.progress": ModuleType("rich.progress"),
        "rich.prompt": ModuleType("rich.prompt"),
        "rich.syntax": ModuleType("rich.syntax"),
        "rich.table": ModuleType("rich.table"),
        "rich.text": ModuleType("rich.text"),
        "rich.tree": ModuleType("rich.tree"),
    }

    stubs["rich.align"].Align = _Dummy
    stubs["rich.columns"].Columns = _Dummy
    stubs["rich.console"].Console = _DummyConsole
    stubs["rich.markdown"].Markdown = _Dummy
    stubs["rich.panel"].Panel = _Dummy
    stubs["rich.progress"].BarColumn = _Dummy
    stubs["rich.progress"].Progress = _Dummy
    stubs["rich.progress"].SpinnerColumn = _Dummy
    stubs["rich.progress"].TaskProgressColumn = _Dummy
    stubs["rich.progress"].TextColumn = _Dummy
    stubs["rich.prompt"].Prompt = _Dummy
    stubs["rich.syntax"].Syntax = _Dummy
    stubs["rich.table"].Table = _Dummy
    stubs["rich.text"].Text = _Dummy
    stubs["rich.tree"].Tree = _Dummy

    sys.modules.update(stubs)


def _install_orun_dependency_stubs() -> None:
    """Install stub modules for heavy orun dependencies used during import."""

    stub_tools = ModuleType("orun.tools")
    stub_tools.TOOL_DEFINITIONS = []
    stub_tools.AVAILABLE_TOOLS = {}
    stub_tools.get_tools_for_model = lambda *_: []

    stub_db = ModuleType("orun.db")
    stub_db.create_conversation = lambda *_, **__: 0
    stub_db.add_message = lambda *_, **__: None
    stub_db.get_conversation_messages = lambda *_: []
    stub_db.get_recent_conversations = lambda *_: []

    stub_prompts_manager = ModuleType("orun.prompts_manager")
    stub_prompts_manager.compose_prompt = lambda **_: types.SimpleNamespace(
        text="", missing=[]
    )

    stub_utils = ModuleType("orun.utils")
    stub_utils.ensure_ollama_running = lambda: None
    stub_utils.read_file_context = lambda *_: ""
    stub_utils.write_clipboard_text = lambda *_: None

    class _StubYoloMode:
        yolo_active = False

        @staticmethod
        def should_skip_confirmation(_):
            return False, ""

        @staticmethod
        def is_command_whitelisted(_):
            return True

    stub_yolo = ModuleType("orun.yolo")
    stub_yolo.yolo_mode = _StubYoloMode()

    sys.modules.setdefault("orun.db", stub_db)
    sys.modules.setdefault("orun.prompts_manager", stub_prompts_manager)
    sys.modules.setdefault("orun.utils", stub_utils)
    sys.modules.setdefault("orun.yolo", stub_yolo)
    sys.modules.setdefault("orun.tools", stub_tools)


sys.modules.setdefault("ollama", mock.MagicMock())
_install_rich_stubs()
_install_orun_dependency_stubs()

from orun import core


def _build_tool_call(name, arguments):
    function = types.SimpleNamespace(name=name, arguments=arguments)
    return types.SimpleNamespace(function=function)


def test_execute_tool_calls_with_string_arguments_parses_json_and_executes():
    messages: list[dict[str, str]] = []

    def dummy_tool(**kwargs):
        return f"received {kwargs['value']}"

    tool_definitions = [
        {
            "type": "function",
            "function": {
                "name": "dummy_tool",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            },
        }
    ]

    with (
        mock.patch.object(core.tools, "AVAILABLE_TOOLS", {"dummy_tool": dummy_tool}),
        mock.patch.object(core.tools, "TOOL_DEFINITIONS", tool_definitions),
        mock.patch.object(core.console, "input", return_value="y"),
        mock.patch.object(core.console, "print"),
    ):
        core.execute_tool_calls(
            [_build_tool_call("dummy_tool", '{"value": "ok"}')], messages
        )

    assert messages[-1]["content"] == "received ok"


def test_execute_tool_calls_reports_malformed_json():
    messages: list[dict[str, str]] = []

    tool_definitions = [
        {
            "type": "function",
            "function": {
                "name": "dummy_tool",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
    ]

    with (
        mock.patch.object(core.tools, "AVAILABLE_TOOLS", {"dummy_tool": lambda **_: ""}),
        mock.patch.object(core.tools, "TOOL_DEFINITIONS", tool_definitions),
        mock.patch.object(core.console, "print"),
    ):
        core.execute_tool_calls(
            [_build_tool_call("dummy_tool", '{"value": ')], messages
        )

    assert "Invalid JSON arguments for tool 'dummy_tool'" in messages[-1]["content"]


def test_execute_tool_calls_reports_missing_required_arguments():
    messages: list[dict[str, str]] = []

    tool_definitions = [
        {
            "type": "function",
            "function": {
                "name": "dummy_tool",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            },
        }
    ]

    with (
        mock.patch.object(core.tools, "AVAILABLE_TOOLS", {"dummy_tool": lambda **_: ""}),
        mock.patch.object(core.tools, "TOOL_DEFINITIONS", tool_definitions),
        mock.patch.object(core.console, "print"),
    ):
        core.execute_tool_calls([_build_tool_call("dummy_tool", {})], messages)

    assert "Missing required argument 'value'" in messages[-1]["content"]


def test_execute_tool_calls_successful_execution_path():
    messages: list[dict[str, str]] = []
    captured: dict[str, str] = {}

    def dummy_tool(**kwargs):
        captured.update(kwargs)
        return "done"

    tool_definitions = [
        {
            "type": "function",
            "function": {
                "name": "dummy_tool",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            },
        }
    ]

    with (
        mock.patch.object(core.tools, "AVAILABLE_TOOLS", {"dummy_tool": dummy_tool}),
        mock.patch.object(core.tools, "TOOL_DEFINITIONS", tool_definitions),
        mock.patch.object(core.console, "input", return_value="y"),
        mock.patch.object(core.console, "print"),
    ):
        core.execute_tool_calls(
            [_build_tool_call("dummy_tool", {"value": "sent"})], messages
        )

    assert captured == {"value": "sent"}
    assert messages[-1]["content"] == "done"
