"""
Consensus module for coordinating multiple models.

Provides sequential and parallel execution strategies with optional tool usage.
"""

from __future__ import annotations

import contextlib
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from threading import Lock
from typing import Dict, List, Optional

import ollama

from orun import db, tools, utils
from orun.consensus_config import consensus_config
from orun.core import execute_tool_calls, handle_ollama_stream
from orun.models_config import models_config
from orun.rich_utils import Colors, console, print_error

# Ensure ollama exposes the generate API even when using lightweight stubs in tests.
if not hasattr(ollama, "generate"):
    def _noop_generate(*_args, **_kwargs) -> None:
        return None

    ollama.generate = _noop_generate  # type: ignore[attr-defined]


@dataclass
class ParallelResponse:
    """Model response returned by parallel consensus execution."""

    model: str
    content: str
    metadata: Dict[str, object]
    error: Optional[str] = None


def unload_model(model_name: str) -> None:
    """
    Unload a model from Ollama memory to free up GPU/RAM resources.
    Uses keep_alive=0 to immediately unload the model.
    """
    try:
        ollama.generate(model=model_name, prompt="", keep_alive=0)
    except Exception:
        # Silently ignore errors - model might already be unloaded.
        pass


def run_consensus(
    pipeline_name: str,
    user_prompt: str,
    image_paths: Optional[List[str]] = None,
    system_prompt: Optional[str] = None,
    tools_enabled: bool = True,
    yolo_mode: bool = False,
    conversation_id: Optional[int] = None,
    model_options: Optional[Dict] = None,
) -> str:
    """
    Entry point for consensus execution. Routes to sequential or parallel mode.
    """
    utils.ensure_ollama_running()

    pipeline = consensus_config.get_pipeline(pipeline_name)
    if not pipeline:
        available = ", ".join([p["name"] for p in consensus_config.list_pipelines()[:5]])
        print_error(f"Pipeline '{pipeline_name}' not found.")
        console.print(f"Available pipelines: {available}...", style=Colors.GREY)
        console.print("Run 'orun consensus' to see all pipelines", style=Colors.GREY)
        return ""

    available_models = models_config.get_models()
    is_valid, error_msg = consensus_config.validate_pipeline(pipeline, available_models)
    if not is_valid:
        print_error("Pipeline validation failed:")
        console.print(error_msg, style=Colors.RED)
        return ""

    if conversation_id is None:
        conversation_id = db.create_conversation(f"consensus:{pipeline_name}")

    pipeline_type = pipeline.get("type", "sequential")
    if pipeline_type == "sequential":
        return run_sequential_consensus(
            pipeline=pipeline,
            pipeline_name=pipeline_name,
            user_prompt=user_prompt,
            image_paths=image_paths,
            system_prompt=system_prompt,
            tools_enabled=tools_enabled,
            conversation_id=conversation_id,
            model_options=model_options,
        )

    if pipeline_type == "parallel":
        return run_parallel_consensus(
            pipeline=pipeline,
            pipeline_name=pipeline_name,
            user_prompt=user_prompt,
            image_paths=image_paths,
            system_prompt=system_prompt,
            tools_enabled=tools_enabled,
            conversation_id=conversation_id,
            model_options=model_options,
        )

    print_error(f"Unknown pipeline type: {pipeline_type}")
    return ""


def run_sequential_consensus(
    pipeline: dict,
    pipeline_name: str,
    user_prompt: str,
    image_paths: Optional[List[str]],
    system_prompt: Optional[str],
    tools_enabled: bool,
    conversation_id: int,
    model_options: Optional[Dict],
) -> str:
    """
    Execute models sequentially, passing context forward between steps.
    """
    console.print(f"\n🔗 Starting consensus pipeline: {pipeline_name}", style=Colors.CYAN)
    console.print(
        f"   Type: Sequential | Models: {len(pipeline['models'])}", style=Colors.GREY
    )

    pipeline_models = pipeline["models"]
    pass_strategy = pipeline.get("pass_strategy", "accumulate")
    total_steps = len(pipeline_models)
    all_messages: List[dict] = []
    final_output = ""

    for step_idx, model_config in enumerate(pipeline_models, 1):
        model_name = model_config["name"]
        role = model_config.get("role", f"step_{step_idx}")
        step_system_prompt = model_config.get("system_prompt")
        step_options = {**model_config.get("options", {})}
        if model_options:
            step_options.update(model_options)

        console.print(
            f"\n[Step {step_idx}/{total_steps}: {role} - {model_name}]",
            style=Colors.MAGENTA,
        )

        step_messages: List[dict] = []
        if step_system_prompt:
            step_messages.append({"role": "system", "content": step_system_prompt})
        elif system_prompt and step_idx == 1:
            step_messages.append({"role": "system", "content": system_prompt})

        if step_idx == 1:
            step_messages.append({"role": "user", "content": user_prompt, "images": image_paths})
        else:
            if pass_strategy == "accumulate":
                step_messages.extend(all_messages)
            elif pass_strategy == "last_only":
                last_assistant = next(
                    (msg for msg in reversed(all_messages) if msg["role"] == "assistant"),
                    None,
                )
                if last_assistant:
                    step_messages.append(
                        {
                            "role": "user",
                            "content": f"Previous step output:\n\n{last_assistant['content']}",
                        }
                    )
            elif pass_strategy == "synthesis":
                assistant_outputs = [
                    msg["content"] for msg in all_messages if msg["role"] == "assistant"
                ]
                if assistant_outputs:
                    synthesis = "\n\n---\n\n".join(assistant_outputs)
                    step_messages.append(
                        {
                            "role": "user",
                            "content": f"Previous steps output:\n\n{synthesis}\n\nNow proceed with your role.",
                        }
                    )

        try:
            tool_defs = tools.get_tools_for_model(model_name) if tools_enabled else None
            response = ollama.chat(
                model=model_name,
                messages=step_messages,
                tools=tool_defs,
                stream=False,
                options=step_options,
            )

            msg = response["message"]
            step_output = msg.get("content", "")

            if msg.get("tool_calls") and tools_enabled:
                step_messages.append(msg)
                execute_tool_calls(msg["tool_calls"], step_messages)
                console.print(f"🤖 [{model_name}] Continuing...", style=Colors.CYAN)
                follow_up_response = ollama.chat(
                    model=model_name,
                    messages=step_messages,
                    stream=True,
                    options=step_options,
                )
                step_output = handle_ollama_stream(follow_up_response)
            else:
                console.print(step_output, style=Colors.GREY)

            step_label = f"[{role} - {model_name}]"
            db.add_message(conversation_id, "assistant", f"{step_label}\n{step_output}")

            all_messages.append(
                {
                    "role": "user",
                    "content": user_prompt if step_idx == 1 else step_output,
                    "images": image_paths if step_idx == 1 else None,
                }
            )
            all_messages.append(
                {
                    "role": "assistant",
                    "content": step_output,
                    "_model": model_name,
                    "_role": role,
                }
            )

            final_output = step_output
            unload_model(model_name)
        except Exception as exc:  # noqa: BLE001
            print_error(
                f"Error in step {step_idx}/{total_steps} ({role} - {model_name}): {exc}"
            )
            console.print(
                f"Pipeline: {pipeline_name}, Step {step_idx}/{total_steps}",
                style=Colors.RED,
            )
            unload_model(model_name)
            return final_output

    console.print(f"\n✓ Consensus pipeline completed ({total_steps} steps)", style=Colors.GREEN)
    return final_output


def _build_parallel_messages(
    user_prompt: str,
    image_paths: Optional[List[str]],
    system_prompt: Optional[str],
    model_config: dict,
) -> List[dict]:
    """Construct a message list for a parallel model invocation."""
    messages: List[dict] = []
    step_system_prompt = model_config.get("system_prompt")
    if step_system_prompt:
        messages.append({"role": "system", "content": step_system_prompt})
    elif system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": user_prompt, "images": image_paths})
    return messages


def run_parallel_consensus(
    pipeline: dict,
    pipeline_name: str,
    user_prompt: str,
    image_paths: Optional[List[str]],
    system_prompt: Optional[str],
    tools_enabled: bool,
    conversation_id: int,
    model_options: Optional[Dict],
) -> str:
    """
    Execute models in parallel using a thread pool, then aggregate results.
    """
    console.print(f"\n🌐 Starting consensus pipeline: {pipeline_name}", style=Colors.CYAN)
    console.print(
        f"   Type: Parallel | Models: {len(pipeline['models'])}", style=Colors.GREY
    )

    models_config_list = pipeline.get("models", [])
    total_models = len(models_config_list)
    if total_models == 0:
        print_error("No models configured for parallel consensus.")
        return ""

    timeout_seconds = float(pipeline.get("timeout_seconds", 120))
    aggregation = pipeline.get("aggregation", {"method": "best_of"})

    db_lock = Lock()
    responses: List[Optional[ParallelResponse]] = [None] * total_models

    def _run_model(model_index: int, model_config: dict) -> ParallelResponse:
        """Run a single model execution with optional tool handling."""
        model_name = model_config["name"]
        step_options = {**model_config.get("options", {})}
        if model_options:
            step_options.update(model_options)

        console.print(
            f"\n[Model {model_index + 1}/{total_models}: {model_name}]",
            style=Colors.MAGENTA,
        )

        messages = _build_parallel_messages(
            user_prompt=user_prompt,
            image_paths=image_paths,
            system_prompt=system_prompt,
            model_config=model_config,
        )
        tool_defs = tools.get_tools_for_model(model_name) if tools_enabled else None

        try:
            connection_ctx = getattr(db.db, "connection_context", None)
            context_value = connection_ctx() if callable(connection_ctx) else None
            connection_context = context_value or contextlib.nullcontext()
            with connection_context:
                response = ollama.chat(
                    model=model_name,
                    messages=messages,
                    tools=tool_defs,
                    stream=False,
                    options=step_options,
                )

            msg = response["message"]
            model_output = msg.get("content", "")

            if msg.get("tool_calls") and tools_enabled:
                messages.append(msg)
                execute_tool_calls(msg["tool_calls"], messages)
                console.print(f"🤖 [{model_name}] Continuing...", style=Colors.CYAN)
                follow_up = ollama.chat(
                    model=model_name,
                    messages=messages,
                    stream=True,
                    options=step_options,
                )
                model_output = handle_ollama_stream(follow_up)
            else:
                console.print(model_output, style=Colors.GREY)

            with db_lock:
                db.add_message(conversation_id, "assistant", f"[{model_name}]\n{model_output}")

            return ParallelResponse(
                model=model_name,
                content=model_output,
                metadata={
                    "model_index": model_index,
                    "role": model_config.get("role"),
                    "options": step_options,
                },
            )
        except Exception as exc:  # noqa: BLE001
            print_error(f"Error with model {model_name}: {exc}")
            return ParallelResponse(
                model=model_name,
                content="",
                metadata={
                    "model_index": model_index,
                    "role": model_config.get("role"),
                    "options": step_options,
                },
                error=str(exc),
            )
        finally:
            with contextlib.suppress(Exception):
                unload_model(model_name)

    with ThreadPoolExecutor(max_workers=total_models) as executor:
        futures: Dict[Future[ParallelResponse], int] = {
            executor.submit(_run_model, idx, model_cfg): idx
            for idx, model_cfg in enumerate(models_config_list)
        }

        done, pending = wait(futures.keys(), timeout=timeout_seconds)

        for future in pending:
            future.cancel()
            meta = futures[future]
            cancelled_model = models_config_list[meta]["name"]
            console.print(
                f"⏳ Cancelled {cancelled_model} after {timeout_seconds:.0f}s timeout",
                style=Colors.YELLOW,
            )

        for future in done:
            model_idx = futures[future]
            if future.cancelled():
                console.print(
                    f"⚠️ {models_config_list[model_idx]['name']} did not complete before cancellation",
                    style=Colors.YELLOW,
                )
                continue

            try:
                result = future.result()
                responses[model_idx] = result
            except Exception as exc:  # noqa: BLE001
                print_error(
                    f"Error collecting result for {models_config_list[model_idx]['name']}: {exc}"
                )

    successful_responses = [
        resp for resp in responses if resp is not None and resp.error is None
    ]
    if not successful_responses:
        print_error("No successful responses from models")
        return ""

    ordered_responses = sorted(successful_responses, key=lambda r: r.metadata.get("model_index", 0))
    serialized_responses = [
        {"model": r.model, "content": r.content, "metadata": r.metadata}
        for r in ordered_responses
    ]

    if aggregation.get("method", "synthesis") == "synthesis":
        return synthesize_responses(
            responses=serialized_responses,
            aggregation=aggregation,
            conversation_id=conversation_id,
            pipeline_name=pipeline_name,
            model_options=model_options,
        )

    if aggregation.get("method") == "best_of":
        console.print(
            f"\n✓ Parallel consensus completed ({len(successful_responses)} responses)",
            style=Colors.GREEN,
        )

        result_parts: List[str] = []
        for idx, resp in enumerate(ordered_responses, 1):
            result_parts.append(f"\n{'=' * 60}\n")
            result_parts.append(f"Response {idx} ({resp.model}):\n")
            result_parts.append(f"{'=' * 60}\n")
            result_parts.append(resp.content)
            result_parts.append("\n")

        return "".join(result_parts)

    print_error(f"Unknown aggregation method: {aggregation.get('method')}")
    return ordered_responses[0].content if ordered_responses else ""


def synthesize_responses(
    responses: List[Dict[str, str]],
    aggregation: dict,
    conversation_id: int,
    pipeline_name: str,
    model_options: Optional[Dict],
) -> str:
    """
    Synthesize multiple responses into one using a synthesizer model.
    """
    synthesizer_model = aggregation.get("synthesizer_model")
    synthesis_prompt = aggregation.get(
        "synthesis_prompt",
        "You have received multiple expert responses to the same question. "
        "Analyze them, identify common insights and disagreements, then provide "
        "a comprehensive synthesis that combines the best aspects of each response.",
    )

    console.print(f"\n🔬 Synthesizing responses with {synthesizer_model}...", style=Colors.CYAN)

    combined = f"{synthesis_prompt}\n\n"
    for idx, resp in enumerate(responses, 1):
        combined += f"--- Response {idx} ({resp['model']}) ---\n"
        combined += resp["content"]
        combined += "\n\n"

    messages = [{"role": "user", "content": combined}]

    try:
        response = ollama.chat(
            model=synthesizer_model,
            messages=messages,
            stream=True,
            options=model_options or {},
        )

        synthesis = handle_ollama_stream(response)
        db.add_message(
            conversation_id,
            "assistant",
            f"[SYNTHESIS - {synthesizer_model}]\n{synthesis}",
        )
        console.print("\n✓ Consensus synthesis completed", style=Colors.GREEN)
        unload_model(synthesizer_model)
        return synthesis

    except Exception as exc:  # noqa: BLE001
        print_error(f"Error during synthesis: {exc}")
        unload_model(synthesizer_model)
        return "\n\n---\n\n".join([r["content"] for r in responses])
