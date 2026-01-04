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
