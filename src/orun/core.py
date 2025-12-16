import ollama
import json
import datetime
from orun import db, utils, tools, prompts_manager
from orun.utils import Colors, print_error, print_warning, print_success, print_info
from orun.yolo import yolo_mode
from orun.rich_utils import console, create_table, print_table, create_panel, print_panel
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.application import run_in_terminal


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
            console.print(f"\n🛠️  AI wants to execute: {func_name}", style=Colors.MAGENTA)
            console.print(f"Arguments: {args}", style=Colors.DIM)

            # Show hint about YOLO mode or whitelist
            if func_name == "run_shell_command" and "command" in args:
                if not yolo_mode.is_command_whitelisted(args["command"]):
                    console.print(f"💡 Tip: Use /yolo to enable YOLO mode or add this command to whitelist", style=Colors.GREY)

            # confirm = input(f"{Colors.YELLOW}Allow? [y/N]: {Colors.RESET}").lower()
            confirm = console.input(f"[yellow]Allow? [y/N]: [/yellow]").lower()

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
                    # Some implementations require tool_call_id, Ollama currently matches by sequence usually
                    # but let's check API specs. For now, simple append works in many cases.
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
                console.print(f"🤖 [{model_name}] Processing tool output...", style=Colors.CYAN)
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


def run_chat_mode(
    model_name: str,
    initial_prompt: str | None,
    initial_images: list[str] | None,
    conversation_id: int | None = None,
    use_tools: bool = False,
    yolo: bool = False,
    initial_prompt_template: str | None = None,
    initial_strategy_template: str | None = None,
):
    """Runs an interactive chat session."""
    utils.ensure_ollama_running()

    # Set YOLO mode if requested
    if yolo:
        yolo_mode.yolo_active = True

    console.print(f"Entering chat mode with '{model_name}'.", style=Colors.GREEN)
    if use_tools:
        console.print(
            "🛠️  Agent Mode Enabled: AI can read/write files and run commands.",
            style=Colors.MAGENTA,
        )

    console.print("💡 Special commands (local, not sent to AI):", style=Colors.DIM)
    console.print("   /yolo        - Toggle YOLO mode (no confirmations)", style=Colors.DIM)
    console.print("   /reload      - Reload configuration", style=Colors.DIM)
    console.print("   /undo        - Undo last turn", style=Colors.DIM)
    console.print("   /save [file] - Save chat to Markdown", style=Colors.DIM)
    console.print("   /run <cmd>   - Run shell command directly", style=Colors.DIM)
    console.print("   /search <q>  - Search the web", style=Colors.DIM)
    console.print("   /explain     - Explain last context", style=Colors.DIM)
    console.print("   /role <name> - Switch persona", style=Colors.DIM)
    console.print("   /prompt <n>  - Apply prompt template", style=Colors.DIM)
    console.print("   /strategy <n>- Apply strategy template", style=Colors.DIM)
    console.print("   /model <name>- Switch model", style=Colors.DIM)
    console.print("   Ctrl+Y       - Toggle YOLO mode (hotkey)", style=Colors.DIM)
    if not use_tools:
        console.print(
            "   (Note: YOLO mode affects only tool-based commands)", style=Colors.GREY
        )
    print("Type 'quit' or 'exit' to end the session.")

    # Start hotkey listener for Ctrl+Y
    # yolo_mode.start_hotkey_listener() # Removed: using prompt_toolkit bindings instead

    # Setup key bindings for Ctrl+Y
    kb = KeyBindings()

    @kb.add(Keys.ControlY, eager=True)
    def _(event):
        "Handle Ctrl+Y key press"

        def toggle_and_print():
            yolo_mode.toggle(show_message=True)

        run_in_terminal(toggle_and_print)

    if conversation_id:
        messages = db.get_conversation_messages(conversation_id)
        console.print(
            f"Loaded {len(messages)} messages from conversation #{conversation_id}",
            style=Colors.GREY,
        )
    else:
        messages = []
        conversation_id = db.create_conversation(model_name)

    tool_defs = tools.TOOL_DEFINITIONS if use_tools else None

    # Helper to process response loop (Assistant -> [Tool -> Assistant]*)
    def process_turn(msgs):
        try:
            if use_tools:
                # First call: No stream to catch tools
                response = ollama.chat(
                    model=model_name, messages=msgs, tools=tool_defs, stream=False
                )
                msg = response["message"]

                msgs.append(msg)  # Add assistant response (content or tool call)

                if msg.get("tool_calls"):
                    execute_tool_calls(msg["tool_calls"], msgs)
                    # Recursive call? Or just loop? Let's loop until no tools.
                    # Simple version: 1-level depth (Tool -> Final Answer).
                    # Complex agents loop. Let's do a simple follow-up stream.

                    console.print("Assistant: ", style=Colors.BLUE, end="")
                    stream = ollama.chat(model=model_name, messages=msgs, stream=True)
                    return handle_ollama_stream(stream)
                else:
                    console.print("Assistant: ", style=Colors.BLUE, end="")
                    console.print(msg["content"])
                    return msg["content"]
            else:
                console.print("Assistant: ", style=Colors.BLUE, end="")
                stream = ollama.chat(model=model_name, messages=msgs, stream=True)
                return handle_ollama_stream(stream)
        except Exception as e:
            print_error(f"Error: {e}")
            return None

    # Handle Initial Prompt
    if initial_prompt or initial_images or initial_prompt_template or initial_strategy_template:
        if not initial_prompt:
            initial_prompt = "Describe this image." if initial_images else ""

        # Build the complete prompt
        full_prompt = initial_prompt
        if initial_prompt_template:
            template = prompts_manager.get_prompt(initial_prompt_template)
            if template:
                full_prompt = f"{template}\n\n{initial_prompt}" if initial_prompt else template
            else:
                print_error(f"Prompt template '{initial_prompt_template}' not found")

        if initial_strategy_template:
            template = prompts_manager.get_strategy(initial_strategy_template)
            if template:
                full_prompt = f"{full_prompt}\n\n{template}" if full_prompt else template
            else:
                print_error(f"Strategy template '{initial_strategy_template}' not found")

        console.print(f"🤖 [{model_name}] Thinking...", style=Colors.CYAN)

        user_message = {
            "role": "user",
            "content": full_prompt,
            "images": initial_images or None,
        }
        messages.append(user_message)
        db.add_message(conversation_id, "user", initial_prompt, initial_images or None)

        resp = process_turn(messages)
        if resp:
            # Note: We aren't saving intermediate tool messages to DB yet to keep history clean/simple for now
            # Only the final text response.
            # Ideally, we should save everything, but peewee schema needs update for structured msgs.
            db.add_message(conversation_id, "assistant", resp)
        else:
            messages.pop()

    # Main Loop
    while True:
        try:
            # Get user input with enhanced key bindings
            # Use prompt_toolkit for Ctrl+Y support
            user_input = pt_prompt(
                "You: ", key_bindings=kb, style="ansigreen"
            )

            if user_input.lower() in ["quit", "exit"]:
                break

            # Handle Ctrl+Y fallback (if key binding didn't catch it and it was entered as text)
            # \x19 is the ASCII code for Ctrl+Y
            if "\x19" in user_input:
                yolo_mode.toggle(show_message=True)
                user_input = user_input.replace("\x19", "").strip()
                if not user_input:
                    continue

            # Handle special commands (these should not be sent to AI)
            cmd_parts = user_input.strip().split(maxsplit=1)
            cmd_root = cmd_parts[0].lower()
            cmd_arg = cmd_parts[1] if len(cmd_parts) > 1 else ""

            if cmd_root == "/yolo":
                yolo_mode.toggle(show_message=True)
                continue

            if cmd_root == "/reload":
                yolo_mode.reload_config()
                continue

            if cmd_root in ["/clear", "/cleat"]: # Handle typo from user request
                messages = []
                conversation_id = db.create_conversation(model_name)
                console.print("\n🧹 Conversation cleared. Started new session.", style=Colors.GREEN)
                continue

            if cmd_root == "/undo":
                if len(messages) >= 2: # Need at least user + assistant
                    # Remove last two from memory
                    if messages[-1]['role'] == 'assistant':
                        messages.pop()
                    if messages and messages[-1]['role'] == 'user':
                        messages.pop()
                    
                    # Remove from DB
                    if db.undo_last_turn(conversation_id):
                        console.print("↩️  Undid last turn.", style=Colors.GREEN)
                    else:
                        console.print("⚠️  Could not undo in database (maybe sync issue).", style=Colors.YELLOW)
                else:
                    console.print("⚠️  Nothing to undo.", style=Colors.YELLOW)
                continue

            if cmd_root == "/save":
                filename = cmd_arg.strip()
                if not filename:
                    filename = f"chat_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                
                try:
                    with open(filename, 'w', encoding='utf-8') as f:
                        for msg in messages:
                            role = msg['role'].upper()
                            content = msg.get('content', '')
                            f.write(f"**{role}**:\n{content}\n\n---\n\n")
                    console.print(f"💾 Saved conversation to {filename}", style=Colors.GREEN)
                except Exception as e:
                    print_error(f"Failed to save: {e}")
                continue

            if cmd_root == "/run":
                if not cmd_arg:
                    print_warning("Usage: /run <command>")
                    continue
                console.print(f"💻 Executing: {cmd_arg}", style=Colors.CYAN)
                result = tools.run_shell_command(cmd_arg)
                console.print(result)
                continue

            if cmd_root == "/explain":
                prompt_text = prompts_manager.get_prompt("explain")
                if prompt_text:
                    console.print("🔍 Asking for explanation...", style=Colors.CYAN)
                    # Treat as user input
                    user_input = prompt_text
                    # Proceed to normal processing
                else:
                    print_error("Explanation prompt not found.")
                    continue

            if cmd_root == "/role":
                if not cmd_arg:
                    print_warning("Usage: /role <name>")
                    print_info(f"Available roles: {', '.join(prompts_manager.list_prompts())}")
                    continue
                
                role_prompt = prompts_manager.get_prompt(cmd_arg)
                if role_prompt:
                    console.print(f"🎭 Applied role: {cmd_arg}", style=Colors.GREEN)
                    # Add as system message or instruction
                    messages.append({'role': 'system', 'content': role_prompt})
                    # db.add_message(conversation_id, 'system', role_prompt) # Schema might not support 'system' yet, skipping DB for now or map to user
                    continue
                else:
                    print_error(f"Role '{cmd_arg}' not found.")
                    continue

            if cmd_root == "/model":
                if not cmd_arg:
                    print_warning(f"Current model: {model_name}")
                    continue

                if db.set_active_model(cmd_arg):
                    # Update local variable to the real full name
                    model_name = db.get_active_model()
                    console.print(f"🤖 Switched to model: {model_name}", style=Colors.GREEN)
                else:
                    print_error(f"Model '{cmd_arg}' not found.")
                    print_info("Available models:")
                    models = db.get_models()
                    for alias, full in models.items():
                        console.print(f"  - [{Colors.GREEN}]{alias}[/{Colors.GREEN}] ({full})")
                continue

            if cmd_root == "/prompt":
                if not cmd_arg:
                    print_warning("Usage: /prompt <name>")
                    print_info(f"Available prompts: {', '.join(prompts_manager.list_prompts())}")
                    continue

                prompt_template = prompts_manager.get_prompt(cmd_arg)
                if prompt_template:
                    console.print(f"📝 Applied prompt: {cmd_arg}", style=Colors.GREEN)
                    # Add as system message
                    messages.append({'role': 'system', 'content': prompt_template})
                    continue
                else:
                    print_error(f"Prompt '{cmd_arg}' not found.")
                    continue

            if cmd_root == "/strategy":
                if not cmd_arg:
                    print_warning("Usage: /strategy <name>")
                    print_info(f"Available strategies: {', '.join(prompts_manager.list_strategies())}")
                    continue

                strategy_template = prompts_manager.get_strategy(cmd_arg)
                if strategy_template:
                    console.print(f"🎯 Applied strategy: {cmd_arg}", style=Colors.GREEN)
                    # Add as system message
                    messages.append({'role': 'system', 'content': strategy_template})
                    continue
                else:
                    print_error(f"Strategy '{cmd_arg}' not found.")
                    continue

            if cmd_root == "/search":
                if not cmd_arg:
                    print_warning("Usage: /search <query>")
                    continue
                console.print(f"🌐 Searching web for: {cmd_arg}", style=Colors.CYAN)
                # Instruct the AI to use its tool capabilities (fetch_url, etc)
                # We format this as a user message to drive the agent
                user_input = f"Search the web for '{cmd_arg}' and provide a summary of the findings."
                # Proceed to normal processing which will treat this as the user prompt

            
            # TODO: Add /temp implementation if we want to pass options to ollama.chat

            console.print(f"🤖 [{model_name}] Thinking...", style=Colors.CYAN)

            # Only add to messages if it's not a special command (already handled above if continued)
            messages.append({"role": "user", "content": user_input})
            db.add_message(conversation_id, "user", user_input)

            resp = process_turn(messages)
            if resp:
                db.add_message(conversation_id, "assistant", resp)
            else:
                messages.pop()

        except EOFError:
            break
        except KeyboardInterrupt:
            console.print("\nChat session interrupted.", style=Colors.YELLOW)
            break
        except Exception as e:
            print()
            print_error(f"Error: {e}")
            if messages and messages[-1]["role"] == "user":
                messages.pop()

    # Stop hotkey listener when chat ends
    # yolo_mode.stop_hotkey_listener()
