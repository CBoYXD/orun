"""
Consensus module for running multiple models together.

Supports:
- Sequential pipelines: Models run one after another, passing context forward
- Parallel aggregation: Models run independently, then results are synthesized
"""

from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from threading import Lock
from typing import Dict, List, Optional
import contextlib
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import ollama

from orun import db, tools, utils
from orun.consensus_config import consensus_config
from orun.core import execute_tool_calls, handle_ollama_stream
from orun.models_config import models_config
from orun.rich_utils import Colors, console, print_error


def unload_model(model_name: str) -> None:
    """
    Unload a model from Ollama memory to free up GPU/RAM resources.
    Uses keep_alive=0 to immediately unload the model.
    """
    try:
        # Setting keep_alive to 0 tells Ollama to unload the model immediately
        ollama.generate(model=model_name, prompt="", keep_alive=0)
    except Exception:
        # Silently ignore errors - model might already be unloaded
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
    Main entry point for consensus execution.
    Routes to sequential or parallel based on pipeline type.
    """
    utils.ensure_ollama_running()

    # Get pipeline configuration
    pipeline = consensus_config.get_pipeline(pipeline_name)
    if not pipeline:
        available = ", ".join(
            [p["name"] for p in consensus_config.list_pipelines()[:5]]
        )
        print_error(f"Pipeline '{pipeline_name}' not found.")
        console.print(f"Available pipelines: {available}...", style=Colors.GREY)
        console.print("Run 'orun consensus' to see all pipelines", style=Colors.GREY)
        return ""

    # Validate pipeline against available models
    available_models = models_config.get_models()
    is_valid, error_msg = consensus_config.validate_pipeline(pipeline, available_models)
    if not is_valid:
        print_error("Pipeline validation failed:")
        console.print(error_msg, style=Colors.RED)
        return ""

    # Create conversation if not provided
    if conversation_id is None:
        conversation_id = db.create_conversation(f"consensus:{pipeline_name}")

    # Route to appropriate execution mode
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
    elif pipeline_type == "parallel":
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
    else:
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
    Execute models sequentially, passing context forward.
    Each model can use tools and see previous models' outputs.
    """
    console.print(
        f"\n🔗 Starting consensus pipeline: {pipeline_name}", style=Colors.CYAN
    )
    console.print(
        f"   Type: Sequential | Models: {len(pipeline['models'])}", style=Colors.GREY
    )

    models_config = pipeline["models"]
    pass_strategy = pipeline.get("pass_strategy", "accumulate")
    total_steps = len(models_config)

    # Initialize message history
    all_messages = []

    # Track final output
    final_output = ""

    for step_idx, model_config in enumerate(models_config, 1):
        model_name = model_config["name"]
        role = model_config.get("role", f"step_{step_idx}")
        step_system_prompt = model_config.get("system_prompt")
        step_options = model_config.get("options", {})

        # Merge with global model_options if provided
        if model_options:
            step_options = {**step_options, **model_options}

        # Print step header
        console.print(
            f"\n[Step {step_idx}/{total_steps}: {role} - {model_name}]",
            style=Colors.MAGENTA,
        )

        # Build messages for this step
        step_messages = []

        # Add step-specific system prompt if provided
        if step_system_prompt:
            step_messages.append({"role": "system", "content": step_system_prompt})
        elif system_prompt and step_idx == 1:
            # Use global system prompt for first step if no step-specific one
            step_messages.append({"role": "system", "content": system_prompt})

        # Determine context to pass based on strategy
        if step_idx == 1:
            # First step: just the user prompt
            step_messages.append(
                {"role": "user", "content": user_prompt, "images": image_paths}
            )
        else:
            # Subsequent steps: apply pass_strategy
            if pass_strategy == "accumulate":
                # Pass all previous messages
                step_messages.extend(all_messages)
            elif pass_strategy == "last_only":
                # Only pass the last assistant response
                if all_messages:
                    # Find last assistant message
                    last_assistant = None
                    for msg in reversed(all_messages):
                        if msg["role"] == "assistant":
                            last_assistant = msg
                            break
                    if last_assistant:
                        step_messages.append(
                            {
                                "role": "user",
                                "content": f"Previous step output:\n\n{last_assistant['content']}",
                            }
                        )
            elif pass_strategy == "synthesis":
                # Synthesize all previous outputs
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

        # Execute this step
        try:
            tool_defs = (
                tools.get_tools_for_model(model_name) if tools_enabled else None
            )

            # First call - might request tools
            response = ollama.chat(
                model=model_name,
                messages=step_messages,
                tools=tool_defs,
                stream=False,
                options=step_options,
            )

            msg = response["message"]
            step_output = msg.get("content", "")

            # Handle tool calls if present
            if msg.get("tool_calls") and tools_enabled:
                # Add assistant's message with tool calls to history
                step_messages.append(msg)

                # Execute tools
                execute_tool_calls(msg["tool_calls"], step_messages)

                # Follow up to get final response
                console.print(f"🤖 [{model_name}] Continuing...", style=Colors.CYAN)

                follow_up_response = ollama.chat(
                    model=model_name,
                    messages=step_messages,
                    stream=True,
                    options=step_options,
                )

                step_output = handle_ollama_stream(follow_up_response)
            else:
                # No tools, just print the output
                console.print(step_output, style=Colors.GREY)

            # Save step output to database
            step_label = f"[{role} - {model_name}]"
            db.add_message(conversation_id, "assistant", f"{step_label}\n{step_output}")

            # Add to message history
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

            # Unload model to free GPU/RAM for next step
            unload_model(model_name)

        except Exception as e:
            error_msg = f"Error in step {step_idx}/{total_steps} ({role} - {model_name}): {str(e)}"
            print_error(error_msg)
            console.print(
                f"Pipeline: {pipeline_name}, Step {step_idx}/{total_steps}",
                style=Colors.RED,
            )
            # Try to unload the model even on error
            unload_model(model_name)
            return final_output  # Return what we have so far

    # Pipeline completed
    console.print(
        f"\n✓ Consensus pipeline completed ({total_steps} steps)", style=Colors.GREEN
    )

    return final_output


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
    Execute models in parallel, aggregate results, and enforce time-bound execution.
    Execute models in parallel using a thread pool, then aggregate results.
    """
    console.print(
        f"\n🌐 Starting consensus pipeline: {pipeline_name}", style=Colors.CYAN
    )
    console.print(
        f"   Type: Parallel | Models: {len(pipeline['models'])}", style=Colors.GREY
    )

    @dataclass
    class ParallelResponse:
        """Container for a model response and associated metadata."""

        model: str
        content: str
        metadata: Dict[str, object]
        error: Optional[str] = None

    models_config = pipeline["models"]
    total_models = len(models_config)
    timeout_seconds = float(pipeline.get("timeout_seconds", 120))

    db_lock = Lock()

    # Collect responses from all models
    responses: List[ParallelResponse] = []

    def _build_messages(model_index: int, model_config: dict) -> List[dict]:
        """
        Build the message payload for an individual model invocation.
        """
        messages: List[dict] = []
        step_system_prompt = model_config.get("system_prompt")
        if step_system_prompt:
            messages.append({"role": "system", "content": step_system_prompt})
        elif system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": user_prompt, "images": image_paths})
        return messages

    def _execute_model(model_index: int, model_config: dict) -> ParallelResponse:
        """
        Invoke a single model with tool handling and thread-safe DB writes.
    # Collect responses from all models in deterministic order
    responses: List[Optional[Dict[str, str]]] = [None] * total_models
    errors: List[Tuple[str, str]] = []
    db_lock = threading.Lock()

    def _run_model(model_idx: int, model_config: dict) -> Dict[str, str]:
        """
        Run a single model execution.


    def _run_model(model_idx: int, model_config: dict) -> Dict[str, str]:
        """
        Run a single model execution.

        Returns a dict with model output or an error string keyed by 'error'.
        """
        model_name = model_config["name"]
        step_options = model_config.get("options", {})

        if model_options:
            step_options = {**step_options, **model_options}

        console.print(
            f"\n[Model {model_index}/{total_models}: {model_name}]",
            style=Colors.MAGENTA,
        )

        try:
            tool_defs = tools.TOOL_DEFINITIONS if tools_enabled else None
            messages = _build_messages(model_index, model_config)

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
            f"\n[Model {model_idx}/{total_models}: {model_name}]",
            style=Colors.MAGENTA,
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt, "images": image_paths})

        try:
            tool_defs = (
                tools.get_tools_for_model(model_name) if tools_enabled else None
            )
            tool_defs = tools.TOOL_DEFINITIONS if tools_enabled else None
            with db.db.connection_context():
                response = ollama.chat(
                    model=model_name,
                    messages=messages,
                    tools=tool_defs,
                    stream=False,
                    options=step_options,
                )

                model_output = handle_ollama_stream(follow_up)
            else:
                console.print(model_output, style=Colors.GREY)

            metadata = {
                "model_index": model_index - 1,
                "role": model_config.get("role"),
                "options": step_options,
            }

            with db_lock:
                db.add_message(
                    conversation_id, "assistant", f"[{model_name}]\n{model_output}"
                )

            unload_model(model_name)

            return ParallelResponse(
                model=model_name, content=model_output, metadata=metadata
            )

                msg = response["message"]
                model_output = msg.get("content", "")

                if msg.get("tool_calls") and tools_enabled:
                    messages.append(msg)
                    execute_tool_calls(msg["tool_calls"], messages)
                    console.print(
                        f"🤖 [{model_name}] Continuing...", style=Colors.CYAN
                    )
                    follow_up = ollama.chat(
                        model=model_name,
                        messages=messages,
                        stream=True,
                        options=step_options,
                    )
                    model_output = handle_ollama_stream(follow_up)
                else:
                    console.print(model_output, style=Colors.GREY)

                # Save to database in a thread-safe manner
                with db_lock:
                    db.add_message(
                        conversation_id, "assistant", f"[{model_name}]\n{model_output}"
                    )

            return {"model": model_name, "content": model_output, "index": model_idx - 1}
        except Exception as exc:  # noqa: BLE001
            error_msg = f"Error with model {model_name}: {str(exc)}"
            print_error(error_msg)
            console.print(
                f"Pipeline: {pipeline_name}, Model {model_index}/{total_models}",
                style=Colors.RED,
            )
            unload_model(model_name)
            return ParallelResponse(
                model=model_name,
                content="",
                metadata={"model_index": model_index - 1, "role": model_config.get("role")},
                error=str(exc),
            )

    with ThreadPoolExecutor(max_workers=total_models) as executor:
        future_to_model: Dict[Future[ParallelResponse], dict] = {
            executor.submit(_execute_model, idx, model_cfg): {
                "model": model_cfg["name"],
                "index": idx,
            }
            for idx, model_cfg in enumerate(models_config, 1)
        }

        done, pending = wait(future_to_model.keys(), timeout=timeout_seconds)

        for future in pending:
            meta = future_to_model[future]
            future.cancel()
            console.print(
                f"⏳ Cancelled {meta['model']} after {timeout_seconds:.0f}s timeout",
                style=Colors.YELLOW,
            )

        for future in done:
            meta = future_to_model[future]
            if future.cancelled():
                console.print(
                    f"⚠️ {meta['model']} did not complete before cancellation",
                    style=Colors.YELLOW,
                )
                continue

            try:
                result = future.result()
                if result.error:
                    continue
                responses.append(result)
            except Exception as exc:  # noqa: BLE001
                print_error(f"Error collecting result for {meta['model']}: {exc}")
            return {"model": model_name, "error": error_msg, "index": model_idx - 1}
        finally:
            with contextlib.suppress(Exception):
                unload_model(model_name)

    max_workers = min(total_models, 8) if total_models > 0 else 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures: List[Future[Dict[str, str]]] = [
            executor.submit(_run_model, idx, model_config)
            for idx, model_config in enumerate(models_config, 1)
        ]

        for future in as_completed(futures):
            result = future.result()
            model_index = result.get("index")
            if result.get("error"):
                errors.append((result["model"], result["error"]))
                continue
            if model_index is not None and model_index < len(responses):
                responses[model_index] = {
                    "model": result["model"],
                    "content": result["content"],
                }

    successful_responses = [resp for resp in responses if resp]

    if not successful_responses:
        print_error("No successful responses from models")
        return ""

    ordered_responses = sorted(
        responses, key=lambda r: r.metadata.get("model_index", 0)
    )
    serialized_responses = [
        {"model": r.model, "content": r.content, "metadata": r.metadata}
        for r in ordered_responses
    ]
    if errors:
        console.print(
            f"\n⚠️  {len(errors)} model(s) failed during consensus. See logs above for details.",
            style=Colors.YELLOW,
        )

    # Aggregation
    aggregation = pipeline.get("aggregation", {})
    method = aggregation.get("method", "synthesis")

    if method == "synthesis":
        return synthesize_responses(
            responses=serialized_responses,
            responses=successful_responses,
            aggregation=aggregation,
            conversation_id=conversation_id,
            pipeline_name=pipeline_name,
            model_options=model_options,
        )
    elif method == "best_of":
        # Return all responses formatted
        console.print(
            f"\n✓ Parallel consensus completed ({len(successful_responses)} responses)",
            style=Colors.GREEN,
        )

        result = ""
        for idx, resp in enumerate(serialized_responses, 1):
        for idx, resp in enumerate(successful_responses, 1):
            result += f"\n{'=' * 60}\n"
            result += f"Response {idx} ({resp['model']}):\n"
            result += f"{'=' * 60}\n"
            result += resp["content"]
            result += "\n"

        return result
    else:
        print_error(f"Unknown aggregation method: {method}")
        return (
            successful_responses[0]["content"] if successful_responses else ""
        )


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

    console.print(
        f"\n🔬 Synthesizing responses with {synthesizer_model}...", style=Colors.CYAN
    )

    # Build synthesis prompt
    combined = f"{synthesis_prompt}\n\n"
    for idx, resp in enumerate(responses, 1):
        combined += f"--- Response {idx} ({resp['model']}) ---\n"
        combined += resp["content"]
        combined += "\n\n"

    # Execute synthesis
    messages = [{"role": "user", "content": combined}]

    try:
        response = ollama.chat(
            model=synthesizer_model,
            messages=messages,
            stream=True,
            options=model_options or {},
        )

        synthesis = handle_ollama_stream(response)

        # Save synthesis
        db.add_message(
            conversation_id,
            "assistant",
            f"[SYNTHESIS - {synthesizer_model}]\n{synthesis}",
        )

        console.print("\n✓ Consensus synthesis completed", style=Colors.GREEN)

        # Unload synthesizer model to free GPU/RAM
        unload_model(synthesizer_model)

        return synthesis

    except Exception as e:
        error_msg = f"Error during synthesis: {str(e)}"
        print_error(error_msg)
        # Try to unload the model even on error
        unload_model(synthesizer_model)
        # Fallback: return all responses
        return "\n\n---\n\n".join([r["content"] for r in responses])
