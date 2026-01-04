"""
Tests for parallel consensus execution.
"""

from __future__ import annotations

import threading
import time

from orun import consensus


def _patch_common(monkeypatch) -> list[tuple[int, str, str, list[str] | None]]:
    """
    Patch shared dependencies to avoid real I/O during tests.
    """
    messages: list[tuple[int, str, str, list[str] | None]] = []
    message_lock = threading.Lock()

    def fake_add_message(
        conversation_id: int, role: str, content: str, images=None
    ) -> None:
        with message_lock:
            messages.append((conversation_id, role, content, images))

    monkeypatch.setattr(consensus.db, "add_message", fake_add_message)
    monkeypatch.setattr(consensus, "execute_tool_calls", lambda *args, **kwargs: None)
    monkeypatch.setattr(consensus, "handle_ollama_stream", lambda response: response)
    monkeypatch.setattr(consensus, "unload_model", lambda *_args, **_kwargs: None)

    return messages


def test_parallel_executor_runs_models_concurrently(monkeypatch):
    """
    Models should run in parallel rather than serially to reduce wall time.
    """
    _patch_common(monkeypatch)

    pipeline = {
        "type": "parallel",
        "models": [{"name": "model_a"}, {"name": "model_b"}],
        "aggregation": {"method": "best_of"},
        "timeout_seconds": 5,
    }

    barrier = threading.Barrier(2)
    delays = {"model_a": 0.3, "model_b": 0.3}

    def fake_chat(*, model: str, **_kwargs):
        barrier.wait()
        time.sleep(delays[model])
        return {"message": {"content": f"output-{model}"}}

    monkeypatch.setattr(consensus.ollama, "chat", fake_chat)

    start = time.perf_counter()
    result = consensus.run_parallel_consensus(
        pipeline=pipeline,
        pipeline_name="test",
        user_prompt="hi",
        image_paths=None,
        system_prompt=None,
        tools_enabled=False,
        conversation_id=1,
        model_options=None,
    )
    elapsed = time.perf_counter() - start

    assert elapsed < sum(delays.values()) * 0.8
    assert "output-model_a" in result
    assert "output-model_b" in result


def test_best_of_preserves_pipeline_order(monkeypatch):
    """
    Aggregation should honor the pipeline model order regardless of completion times.
    """
    _patch_common(monkeypatch)

    pipeline = {
        "type": "parallel",
        "models": [{"name": "slow_model"}, {"name": "fast_model"}],
        "aggregation": {"method": "best_of"},
        "timeout_seconds": 5,
    }

    delays = {"slow_model": 0.2, "fast_model": 0.05}
    outputs = {"slow_model": "slow-response", "fast_model": "fast-response"}

    def fake_chat(*, model: str, **_kwargs):
        time.sleep(delays[model])
        return {"message": {"content": outputs[model]}}

    monkeypatch.setattr(consensus.ollama, "chat", fake_chat)

    result = consensus.run_parallel_consensus(
        pipeline=pipeline,
        pipeline_name="test",
        user_prompt="hi",
        image_paths=None,
        system_prompt=None,
        tools_enabled=False,
        conversation_id=2,
        model_options=None,
    )

    first_idx = result.index("Response 1 (slow_model)")
    second_idx = result.index("Response 2 (fast_model)")

    assert first_idx < second_idx
    assert "slow-response" in result
    assert "fast-response" in result


def test_synthesis_receives_ordered_responses(monkeypatch):
    """
    Synthesis should receive responses ordered by pipeline definition.
    """
    _patch_common(monkeypatch)

    pipeline = {
        "type": "parallel",
        "models": [{"name": "first"}, {"name": "second"}],
        "aggregation": {"method": "synthesis", "synthesizer_model": "synth"},
        "timeout_seconds": 5,
    }

    delays = {"first": 0.05, "second": 0.01}
    outputs = {"first": "first-output", "second": "second-output"}
    captured = {}

    def fake_chat(*, model: str, **_kwargs):
        time.sleep(delays[model])
        return {"message": {"content": outputs[model]}}

    def fake_synthesize(responses, aggregation, conversation_id, pipeline_name, model_options):
        captured["responses"] = responses
        return "synthetic-result"

    monkeypatch.setattr(consensus.ollama, "chat", fake_chat)
    monkeypatch.setattr(consensus, "synthesize_responses", fake_synthesize)

    result = consensus.run_parallel_consensus(
        pipeline=pipeline,
        pipeline_name="test",
        user_prompt="hi",
        image_paths=None,
        system_prompt=None,
        tools_enabled=False,
        conversation_id=3,
        model_options=None,
    )

    assert result == "synthetic-result"
    assert [resp["model"] for resp in captured["responses"]] == ["first", "second"]
    assert all("metadata" in resp for resp in captured["responses"])
