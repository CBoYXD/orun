from contextlib import nullcontext
from typing import Dict, List, Optional
import types

from orun import consensus, tools


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
    monkeypatch.setattr(
        consensus.db,
        "db",
        types.SimpleNamespace(connection_context=lambda: nullcontext()),
    )
    monkeypatch.setattr(consensus, "unload_model", lambda *_: None)

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
