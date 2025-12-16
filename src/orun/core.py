import json

import ollama

from orun import db, prompts_manager, tools, utils
from orun.rich_utils import console
from orun.utils import Colors, print_error, print_warning
from orun.yolo import yolo_mode


def handle_ollama_stream(stream) -> str:
    """Prints the stream and returns the full response."""
    full_response = ""
    try:
        for chunk in stream:
            content = chunk["message"]["content"]
            console.print(content, end="", flush=True, style=Colors.GREY)
            full_response += content
    except Exception as e:
        console.print()  # Newline
        print_error(f"Stream Error: {e}")
    finally:
        console.print()
    return full_response


def execute_tool_calls(tool_calls, messages):
    """Executes tool calls with user confirmation and updates messages."""
    for tool in tool_calls:
        func_name = tool.function.name
        args = tool.function.arguments

        # Args can be a dict or a JSON string depending on the model/library version
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                pass  # It might be a malformed string or actually a dict disguised

        # Special handling for shell commands with YOLO mode
        should_confirm = True
        if func_name == "run_shell_command" and "command" in args:
            command = args["command"]

            # Check if we should skip confirmation (whitelisted or YOLO mode)
            skip_confirm, skip_reason = yolo_mode.should_skip_confirmation(command)

            # If command is blocked
            if "BLOCKED" in skip_reason:
                console.print(f"\n❌ {skip_reason}", style=Colors.RED)
                messages.append(
                    {"role": "tool", "content": f"Command blocked: {skip_reason}"}
                )
                continue

            # Skip confirmation if needed
            if skip_confirm:
                should_confirm = False
                console.print(f"\n🛠️  AI executing: {func_name}", style=Colors.MAGENTA)
                console.print(f"Arguments: {args}", style=Colors.DIM)
                if "WHITELISTED" in skip_reason:
                    console.print(skip_reason, style=Colors.GREEN)
                elif "YOLO MODE" in skip_reason:
                    console.print(skip_reason, style=Colors.YELLOW)

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
        func = tools.AVAILABLE_TOOLS.get(func_name)
        if func:
            console.print("Running...", style=Colors.DIM)
            result = func(**args)

            # Check if result is excessively long (e.g. reading a huge file)
            preview = result[:100] + "..." if len(result) > 100 else result
            console.print(f"Result: {preview}", style=Colors.DIM)

            messages.append(
                {
                    "role": "tool",
                    "content": str(result),
                }
            )
        else:
            print_error(f"Tool '{func_name}' not found.")
            messages.append(
                {"role": "tool", "content": f"Error: Tool '{func_name}' not found."}
            )


def run_single_shot(
    model_name: str,
    user_prompt: str,
    image_paths: list[str] | None,
    use_tools: bool = False,
    yolo: bool = False,
    prompt_template: str | None = None,
    strategy_template: str | None = None,
):
    """Handles a single query to the model."""
    utils.ensure_ollama_running()

    # Set YOLO mode if requested
    if yolo:
        yolo_mode.yolo_active = True
        console.print("🔥 YOLO MODE ENABLED for this command", style=Colors.RED)

    console.print(f"🤖 [{model_name}] Thinking...", style=Colors.CYAN)

    conversation_id = db.create_conversation(model_name)

    # Build the complete prompt
    full_prompt = user_prompt
    if prompt_template:
        template = prompts_manager.get_prompt(prompt_template)
        if template:
            full_prompt = f"{template}\n\n{user_prompt}" if user_prompt else template
        else:
            print_error(f"Prompt template '{prompt_template}' not found")

    if strategy_template:
        template = prompts_manager.get_strategy(strategy_template)
        if template:
            full_prompt = f"{full_prompt}\n\n{template}" if full_prompt else template
        else:
            print_error(f"Strategy template '{strategy_template}' not found")

    db.add_message(conversation_id, "user", full_prompt, image_paths or None)

    messages = [{"role": "user", "content": full_prompt, "images": image_paths or None}]

    # Tool definitions
    tool_defs = tools.TOOL_DEFINITIONS if use_tools else None

    try:
        # If using tools, we can't easily stream the first response because we need to parse JSON first
        if use_tools:
            response = ollama.chat(
                model=model_name, messages=messages, tools=tool_defs, stream=False
            )
            msg = response["message"]

            # Check for tool calls
            if msg.get("tool_calls"):
                # Add assistant's "thought" or empty tool call request to history
                messages.append(msg)

                execute_tool_calls(msg["tool_calls"], messages)

                # Follow up with the tool outputs
                console.print(
                    f"🤖 [{model_name}] Processing tool output...", style=Colors.CYAN
                )
                stream = ollama.chat(model=model_name, messages=messages, stream=True)
                final_response = handle_ollama_stream(stream)
                if final_response:
                    db.add_message(conversation_id, "assistant", final_response)
            else:
                # Normal response
                console.print(msg["content"])
                db.add_message(conversation_id, "assistant", msg["content"])
        else:
            # Standard streaming
            stream = ollama.chat(model=model_name, messages=messages, stream=True)
            response = handle_ollama_stream(stream)
            if response:
                db.add_message(conversation_id, "assistant", response)

    except Exception as e:
        console.print()
        print_error(f"Error: {e}")
    finally:
        # Reset YOLO mode if it was enabled for this command
        if yolo:
            yolo_mode.yolo_active = False
