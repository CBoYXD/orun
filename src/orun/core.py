import json
from pathlib import Path

import ollama

from orun import config as orun_config
from orun import db, prompts_manager, tools, utils
from orun.rich_utils import Colors, console, print_error, print_warning
from orun.yolo import yolo_mode


def handle_ollama_stream(stream, silent: bool = False) -> str:
    """Prints the stream and returns the full response."""
    full_response = ""
    try:
        for chunk in stream:
            content = chunk["message"]["content"]
            if not silent:
                console.print(content, end="", flush=True, style=Colors.GREY)
            full_response += content
    except Exception as e:
        if not silent:
            console.print()  # Newline
        print_error(f"Stream Error: {e}")
    finally:
        if not silent:
            console.print()
    return full_response


def _get_function_gemma_model_name() -> str | None:
    try:
        response = ollama.list()
        if hasattr(response, "models"):
            models = response.models
        elif isinstance(response, dict):
            models = response.get("models", [])
        else:
            models = []

        for model in models:
            name = ""
            if hasattr(model, "model"):
                name = model.model
            elif hasattr(model, "name"):
                name = model.name
            elif isinstance(model, dict):
                name = model.get("model", model.get("name", ""))

            if "functiongemma" in name.lower():
                return name
    except Exception:
        return None
    return None


def run_function_gemma_task(task_description: str, context: str = "") -> str:
    full_prompt = f"Task: {task_description}".strip()
    if context:
        full_prompt = f"{context}\n\n{full_prompt}"

    model_name = _get_function_gemma_model_name()
    if not model_name:
        return (
            "FunctionGemma model is not available. "
            "To enable advanced tool calling, run: ollama pull functiongemma:270m"
        )

    messages = [{"role": "user", "content": full_prompt}]
    tool_defs = tools.get_tools_for_model(model_name)

    response = ollama.chat(
        model=model_name, messages=messages, tools=tool_defs, stream=False
    )
    msg = response["message"]

    if msg.get("tool_calls"):
        messages.append(msg)
        execute_tool_calls(msg["tool_calls"], messages)
        response = ollama.chat(model=model_name, messages=messages, stream=False)
        return response["message"]["content"]

    return msg.get("content", "")


def execute_tool_calls(tool_calls, messages):
    """
    Executes tool calls with user confirmation and updates messages.

    Notes on shell commands:
    - Whitelisted commands can execute without confirmation.
    - YOLO mode skips confirmation but still enforces allowlist/denylist checks.
    """
    limits = orun_config.get_section("limits")
    preview_limit = limits.get("tool_preview_chars", 200)

    for tool in tool_calls:
        func_name = tool.function.name
        args = tool.function.arguments

        # Args can be a dict or a JSON string depending on the model/library version
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                pass  # It might be a malformed string or actually a dict disguised

        # Skip displaying call_function_model - it's just a proxy to FunctionGemma
        # We show the actual tool calls from FunctionGemma instead
        is_proxy_call = func_name == "call_function_model"

        # Special handling for shell commands with YOLO mode and allow/deny lists
        should_confirm = True
        if func_name == "run_shell_command" and "command" in args:
            command = args["command"]

            # Check if we should skip confirmation (whitelisted or YOLO mode)
            skip_confirm, skip_reason = yolo_mode.should_skip_confirmation(command)

            if not skip_confirm:
                # Warn when denylist blocks even before confirmation
                allowed, denial_reason = tools.is_shell_command_allowed(command)
                if not allowed:
                    console.print(f"\n❌ {denial_reason}", style=Colors.RED)
                    messages.append(
                        {"role": "tool", "content": f"Command blocked: {denial_reason}"}
                    )
                    continue

            # Skip confirmation if needed
            if skip_confirm:
                should_confirm = False
                if not is_proxy_call:  # Don't show proxy calls
                    console.print(f"\n🛠️  AI executing: {func_name}", style=Colors.MAGENTA)
                    console.print(f"Arguments: {args}", style=Colors.DIM)
                    if "WHITELISTED" in skip_reason:
                        console.print(skip_reason, style=Colors.GREEN)
                    elif "YOLO MODE" in skip_reason:
                        console.print(skip_reason, style=Colors.YELLOW)
                        console.print(
                            "Note: Allowlist/denylist still enforced even in YOLO mode.",
                            style=Colors.GREY,
                        )

        # Skip confirmation for proxy calls (call_function_model)
        if is_proxy_call:
            should_confirm = False

        # Confirmation Prompt (or display if auto-confirming)
        if should_confirm:
            console.print(
                f"\n🛠️  AI wants to execute: {func_name}", style=Colors.MAGENTA
            )
            console.print(f"Arguments: {args}", style=Colors.DIM)

            # Show hint about YOLO mode or whitelist
            if func_name == "run_shell_command" and "command" in args:
                if not yolo_mode.is_command_whitelisted(args["command"]):
                    console.print(
                        "💡 Tip: Use /yolo to enable YOLO mode or add this command to whitelist",
                        style=Colors.GREY,
                    )

            confirm = console.input("[yellow]Allow? [y/N]: [/yellow]").lower()

            if confirm != "y":
                print_warning("Tool execution denied.")
                messages.append(
                    {"role": "tool", "content": "User denied tool execution."}
                )
                continue

        # Execute the tool
        result = None
        if func_name == "call_function_model":
            if isinstance(args, dict):
                result = run_function_gemma_task(
                    args.get("task_description", ""), args.get("context", "")
                )
            else:
                result = run_function_gemma_task(str(args), "")
        else:
            func = tools.AVAILABLE_TOOLS.get(func_name)
            if func:
                console.print("Running...", style=Colors.DIM)
                result = func(**args)
            else:
                print_error(f"Tool '{func_name}' not found.")
                messages.append(
                    {
                        "role": "tool",
                        "content": f"Error: Tool '{func_name}' not found.",
                    }
                )
                continue

        if result is not None:
            result_text = str(result)
            preview = (
                result_text[:preview_limit] + "..."
                if preview_limit and len(result_text) > preview_limit
                else result_text
            )
            # Don't show result for proxy calls - FunctionGemma will show its own tool results
            if not is_proxy_call:
                console.print(f"Result: {preview}", style=Colors.DIM)
            messages.append({"role": "tool", "content": result_text})


def run_single_shot(
    model_name: str,
    user_prompt: str,
    image_paths: list[str] | None,
    use_tools: bool = False,
    yolo: bool = False,
    prompt_template: str | None = None,
    strategy_template: str | None = None,
    file_paths: list[str] | None = None,
    stdin_content: str | None = None,
    output_file: str | None = None,
    system_prompt: str | None = None,
    dir_context: str | None = None,
    clipboard_content: str | None = None,
    to_clipboard: bool = False,
    model_options: dict | None = None,
    quiet: bool = False,
):
    """Handles a single query to the model."""
    utils.ensure_ollama_running()

    # Set YOLO mode if requested
    if yolo:
        yolo_mode.yolo_active = True
        if not quiet:
            console.print("🔥 YOLO MODE ENABLED for this command", style=Colors.RED)

    if not quiet:
        console.print(f"🤖 [{model_name}] Thinking...", style=Colors.CYAN)

    conversation_id = db.create_conversation(model_name)

    # Build the complete prompt
    build = prompts_manager.compose_prompt(
        user_prompt=user_prompt,
        prompt_template=prompt_template,
        strategy_template=strategy_template,
    )

    for missing in build.missing:
        print_error(f"Template {missing} not found")

    full_prompt = build.text

    # Add clipboard content if provided
    if clipboard_content:
        clipboard_prefix = "--- Input from clipboard ---\n"
        full_prompt = (
            f"{clipboard_prefix}{clipboard_content}\n\n{full_prompt}"
            if full_prompt
            else f"{clipboard_prefix}{clipboard_content}"
        )

    # Add stdin content if provided (pipe input)
    if stdin_content:
        stdin_prefix = "--- Input from stdin ---\n"
        full_prompt = (
            f"{stdin_prefix}{stdin_content}\n\n{full_prompt}"
            if full_prompt
            else f"{stdin_prefix}{stdin_content}"
        )

    # Add directory context if provided
    if dir_context:
        full_prompt = f"{dir_context}\n\n{full_prompt}" if full_prompt else dir_context

    # Add file context if provided
    if file_paths:
        file_context = utils.read_file_context(file_paths)
        if file_context:
            full_prompt = (
                f"{file_context}\n\n{full_prompt}" if full_prompt else file_context
            )

    db.add_message(conversation_id, "user", full_prompt, image_paths or None)

    # Build messages array with optional system prompt
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append(
        {"role": "user", "content": full_prompt, "images": image_paths or None}
    )

    # Tool definitions (filtered by model type)
    tool_defs = tools.get_tools_for_model(model_name) if use_tools else None

    # Variable to hold the final output
    final_output = ""

    try:
        # If using tools, we can't easily stream the first response because we need to parse JSON first
        if use_tools:
            response = ollama.chat(
                model=model_name,
                messages=messages,
                tools=tool_defs,
                stream=False,
                options=model_options,
            )
            msg = response["message"]

            # Check for tool calls
            if msg.get("tool_calls"):
                # Add assistant's "thought" or empty tool call request to history
                messages.append(msg)

                execute_tool_calls(msg["tool_calls"], messages)

                # Follow up with the tool outputs
                if not output_file and not quiet:
                    console.print(
                        f"🤖 [{model_name}] Processing tool output...",
                        style=Colors.CYAN,
                    )
                stream = ollama.chat(
                    model=model_name,
                    messages=messages,
                    stream=True,
                    options=model_options,
                )
                final_response = handle_ollama_stream(
                    stream, silent=(bool(output_file) or quiet)
                )
                if final_response:
                    db.add_message(conversation_id, "assistant", final_response)
                    final_output = final_response
            else:
                # Normal response
                if not output_file and not quiet:
                    console.print(msg["content"])
                db.add_message(conversation_id, "assistant", msg["content"])
                final_output = msg["content"]
        else:
            # Standard streaming
            stream = ollama.chat(
                model=model_name, messages=messages, stream=True, options=model_options
            )
            response = handle_ollama_stream(stream, silent=(bool(output_file) or quiet))
            if response:
                db.add_message(conversation_id, "assistant", response)
                final_output = response

        # Save to file if requested
        if output_file and final_output:
            try:
                output_path = Path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(final_output, encoding="utf-8")
                if not quiet:
                    console.print(
                        f"\n✅ Output saved to: {output_file}", style=Colors.GREEN
                    )
            except Exception as e:
                print_error(f"Failed to save output to file: {e}")

        # Copy to clipboard if requested
        if to_clipboard and final_output:
            utils.write_clipboard_text(final_output)

    except Exception as e:
        console.print()
        print_error(f"Error: {e}")
    finally:
        # Reset YOLO mode if it was enabled for this command
        if yolo:
            yolo_mode.yolo_active = False

    return final_output


def run_continue_shot(
    conversation_id: int,
    user_prompt: str,
    image_paths: list[str] | None,
    model_name: str,
    use_tools: bool = False,
    yolo: bool = False,
    output_file: str | None = None,
    model_options: dict | None = None,
):
    """Continue an existing conversation in single-shot mode."""
    utils.ensure_ollama_running()

    # Set YOLO mode if requested
    if yolo:
        yolo_mode.yolo_active = True
        console.print("🔥 YOLO MODE ENABLED for this command", style=Colors.RED)

    # Load conversation history
    conv = db.get_conversation(conversation_id)
    if not conv:
        print_error(f"Conversation #{conversation_id} not found.")
        return

    console.print(
        f"🤖 [{model_name}] Continuing conversation #{conversation_id}...",
        style=Colors.CYAN,
    )

    # Build messages from history
    messages = []
    for msg in db.get_conversation_messages(conversation_id):
        message_dict = {"role": msg["role"], "content": msg["content"]}
        if msg.get("images"):
            message_dict["images"] = msg["images"]
        messages.append(message_dict)

    # Add new user message
    if user_prompt or image_paths:
        db.add_message(conversation_id, "user", user_prompt or "", image_paths or None)
        messages.append(
            {
                "role": "user",
                "content": user_prompt or "",
                "images": image_paths or None,
            }
        )

    # Tool definitions (filtered by model type)
    tool_defs = tools.get_tools_for_model(model_name) if use_tools else None

    # Variable to hold the final output
    final_output = ""

    try:
        # If using tools, we can't easily stream the first response because we need to parse JSON first
        if use_tools:
            response = ollama.chat(
                model=model_name,
                messages=messages,
                tools=tool_defs,
                stream=False,
                options=model_options,
            )
            msg = response["message"]

            # Check for tool calls
            if msg.get("tool_calls"):
                # Add assistant's "thought" or empty tool call request to history
                messages.append(msg)

                execute_tool_calls(msg["tool_calls"], messages)

                # Follow up with the tool outputs
                if not output_file:
                    console.print(
                        f"🤖 [{model_name}] Processing tool output...",
                        style=Colors.CYAN,
                    )
                stream = ollama.chat(
                    model=model_name,
                    messages=messages,
                    stream=True,
                    options=model_options,
                )
                final_response = handle_ollama_stream(stream, silent=bool(output_file))
                if final_response:
                    db.add_message(conversation_id, "assistant", final_response)
                    final_output = final_response
            else:
                # Normal response
                if not output_file:
                    console.print(msg["content"])
                db.add_message(conversation_id, "assistant", msg["content"])
                final_output = msg["content"]
        else:
            # Standard streaming
            stream = ollama.chat(
                model=model_name, messages=messages, stream=True, options=model_options
            )
            response = handle_ollama_stream(stream, silent=bool(output_file))
            if response:
                db.add_message(conversation_id, "assistant", response)
                final_output = response

        # Save to file if requested
        if output_file and final_output:
            try:
                output_path = Path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(final_output, encoding="utf-8")
                console.print(
                    f"\n✅ Output saved to: {output_file}", style=Colors.GREEN
                )
            except Exception as e:
                print_error(f"Failed to save output to file: {e}")

    except Exception as e:
        console.print()
        print_error(f"Error: {e}")
    finally:
        # Reset YOLO mode if it was enabled for this command
        if yolo:
            yolo_mode.yolo_active = False
