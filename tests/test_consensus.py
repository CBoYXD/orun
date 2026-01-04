from pathlib import Path
from typing import Dict, List, Optional

import sys
import types

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

ollama_stub = types.ModuleType("ollama")
ollama_stub.chat = lambda *args, **kwargs: None
ollama_stub.generate = lambda *args, **kwargs: None
sys.modules["ollama"] = ollama_stub

db_stub = types.ModuleType("orun.db")
db_stub.add_message = lambda *args, **kwargs: None
db_stub.create_conversation = lambda *args, **kwargs: 0
sys.modules["orun.db"] = db_stub

utils_stub = types.ModuleType("orun.utils")
utils_stub.ensure_ollama_running = lambda: None
sys.modules["orun.utils"] = utils_stub

tools_stub = types.ModuleType("orun.tools")
tools_stub.TOOL_DEFINITIONS = [
    {"function": {"name": "call_function_model"}},
    {"function": {"name": "write_file"}},
    {"function": {"name": "read_file"}},
]


def _get_tools_for_model(model_name: str) -> list[dict]:
    is_function_gemma = (
        "functiongemma" in model_name.lower() or "function-gemma" in model_name.lower()
    )
    if is_function_gemma:
        return [
            tool
            for tool in tools_stub.TOOL_DEFINITIONS
            if tool["function"]["name"] != "call_function_model"
        ]
    return [
        tool
        for tool in tools_stub.TOOL_DEFINITIONS
        if tool["function"]["name"] == "call_function_model"
    ]


tools_stub.get_tools_for_model = _get_tools_for_model
sys.modules["orun.tools"] = tools_stub

rich_utils_stub = types.ModuleType("orun.rich_utils")
rich_utils_stub.Colors = types.SimpleNamespace(
    GREY="grey", CYAN="cyan", MAGENTA="magenta", RED="red", GREEN="green"
)
rich_utils_stub.console = types.SimpleNamespace(print=lambda *args, **kwargs: None)
rich_utils_stub.print_error = lambda *args, **kwargs: None
rich_utils_stub.print_warning = lambda *args, **kwargs: None
rich_utils_stub.print_success = lambda *args, **kwargs: None
sys.modules["orun.rich_utils"] = rich_utils_stub

import orun.consensus as consensus
from orun import tools


def test_parallel_consensus_advertises_tools_per_model(monkeypatch) -> None:
    """
    Ensure FunctionGemma models get full tool access while other models only
    receive the delegation tool during parallel consensus execution.
    """

    captured_tools: Dict[str, Optional[List[dict]]] = {}
    function_model = "function-gemma:2b"
    standard_model = "llama3"

    expected_function_tools = {
        tool["function"]["name"] for tool in tools.get_tools_for_model(function_model)
    }
    expected_standard_tools = {
        tool["function"]["name"] for tool in tools.get_tools_for_model(standard_model)
    }

    def fake_chat(
        model: str,
        messages: list[dict],
        tools: Optional[List[dict]] = None,
        stream: bool = False,
        options: Optional[dict] = None,
    ) -> dict:
        captured_tools[model] = tools
        return {"message": {"content": f"response from {model}"}}

    monkeypatch.setattr(consensus.ollama, "chat", fake_chat)
    monkeypatch.setattr(consensus.ollama, "generate", lambda *args, **kwargs: None)
    monkeypatch.setattr(consensus.db, "add_message", lambda *args, **kwargs: None)

    pipeline = {
        "models": [{"name": function_model}, {"name": standard_model}],
        "aggregation": {"method": "best_of"},
    }

    consensus.run_parallel_consensus(
        pipeline=pipeline,
        pipeline_name="test-pipeline",
        user_prompt="Hello, world!",
        image_paths=None,
        system_prompt=None,
        tools_enabled=True,
        conversation_id=1,
        model_options=None,
    )

    assert captured_tools[function_model] is not None
    assert captured_tools[standard_model] is not None
    assert {
        tool["function"]["name"] for tool in captured_tools[function_model] or []
    } == expected_function_tools
    assert {
        tool["function"]["name"] for tool in captured_tools[standard_model] or []
    } == expected_standard_tools
    assert captured_tools[function_model] != captured_tools[standard_model]
