import ollama
import json
import datetime
from pathlib import Path
from orun import db, utils, tools, prompts_manager
from orun.utils import Colors, colored, print_error, print_warning, print_success, print_info
from orun.yolo import yolo_mode
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.application import run_in_terminal


def handle_ollama_stream(stream) -> str:
    """Prints the stream and returns the full response."""
    full_response = ""
    try:
        for chunk in stream:
            content = chunk["message"]["content"]
            print(content, end="", flush=True)
            full_response += content
    except Exception as e:
        print()  # Newline
        print_error(f"Stream Error: {e}")
    finally:
        print()
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
                print(f"\n{Colors.RED}❌ {skip_reason}{Colors.RESET}")
                messages.append(
                    {"role": "tool", "content": f"Command blocked: {skip_reason}"}
                )
                continue

            # Skip confirmation if needed
            if skip_confirm:
                should_confirm = False
                print(
                    f"\n{Colors.MAGENTA}🛠️  AI executing:{Colors.RESET} {Colors.CYAN}{func_name}{Colors.RESET}"
                )
                print(f"{Colors.GREY}Arguments: {args}{Colors.RESET}")
                if "WHITELISTED" in skip_reason:
                    print(f"{Colors.GREEN}{skip_reason}{Colors.RESET}")
                elif "YOLO MODE" in skip_reason:
                    print(f"{Colors.YELLOW}{skip_reason}{Colors.RESET}")

        # Confirmation Prompt (or display if auto-confirming)
        if should_confirm:
            print(
                f"\n{Colors.MAGENTA}🛠️  AI wants to execute:{Colors.RESET} {Colors.CYAN}{func_name}{Colors.RESET}"
            )
            print(f"{Colors.GREY}Arguments: {args}{Colors.RESET}")

            # Show hint about YOLO mode or whitelist
            if func_name == "run_shell_command" and "command" in args:
                if not yolo_mode.is_command_whitelisted(args["command"]):
                    print(
                        f"{Colors.GREY}💡 Tip: Use /yolo to enable YOLO mode or add this command to whitelist{Colors.RESET}"
                    )

            confirm = input(f"{Colors.YELLOW}Allow? [y/N]: {Colors.RESET}").lower()

            if confirm != "y":
                print_warning("Tool execution denied.")
                messages.append(
                    {"role": "tool", "content": "User denied tool execution."}
                )
                continue

        # Execute the tool
        func = tools.AVAILABLE_TOOLS.get(func_name)
        if func:
            print(f"{Colors.GREY}Running...{Colors.RESET}")
            result = func(**args)

            # Check if result is excessively long (e.g. reading a huge file)
            preview = result[:100] + "..." if len(result) > 100 else result
            print(f"{Colors.GREY}Result: {preview}{Colors.RESET}")

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
):
    """Handles a single query to the model."""
    utils.ensure_ollama_running()

    # Set YOLO mode if requested
    if yolo:
        yolo_mode.yolo_active = True
        print(colored("🔥 YOLO MODE ENABLED for this command", Colors.RED))

    print(colored(f"🤖 [{model_name}] Thinking...", Colors.CYAN))

    conversation_id = db.create_conversation(model_name)
    db.add_message(conversation_id, "user", user_prompt, image_paths or None)

    messages = [{"role": "user", "content": user_prompt, "images": image_paths or None}]

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
                print(
                    colored(f"🤖 [{model_name}] Processing tool output...", Colors.CYAN)
                )
                stream = ollama.chat(model=model_name, messages=messages, stream=True)
                final_response = handle_ollama_stream(stream)
                if final_response:
                    db.add_message(conversation_id, "assistant", final_response)
            else:
                # Normal response
                print(msg["content"])
                db.add_message(conversation_id, "assistant", msg["content"])
        else:
            # Standard streaming
            stream = ollama.chat(model=model_name, messages=messages, stream=True)
            response = handle_ollama_stream(stream)
            if response:
                db.add_message(conversation_id, "assistant", response)

    except Exception as e:
        print()
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
):
    """Runs an interactive chat session."""
    utils.ensure_ollama_running()

    # Set YOLO mode if requested
    if yolo:
        yolo_mode.yolo_active = True

    print(colored(f"Entering chat mode with '{model_name}'.", Colors.GREEN))
    if use_tools:
        print(
            colored(
                "🛠️  Agent Mode Enabled: AI can read/write files and run commands.",
                Colors.MAGENTA,
            )
        )

    print(colored("💡 Special commands (local, not sent to AI):", Colors.GREY))
    print(colored("   /yolo        - Toggle YOLO mode (no confirmations)", Colors.GREY))
    print(colored("   /clear       - Clear conversation history", Colors.GREY))
    print(colored("   /undo        - Undo last turn", Colors.GREY))
    print(colored("   /save [file] - Save chat to Markdown", Colors.GREY))
    print(colored("   /run <cmd>   - Run shell command directly", Colors.GREY))
    print(colored("   /search <q>  - Search the web", Colors.GREY))
    print(colored("   /explain     - Explain last context", Colors.GREY))
    print(colored("   /role <name> - Switch persona", Colors.GREY))
    print(colored("   /model <name>- Switch model", Colors.GREY))
    print(colored("   Ctrl+Y       - Toggle YOLO mode (hotkey)", Colors.GREY))
    if not use_tools:
        print(
            colored(
                "   (Note: YOLO mode affects only tool-based commands)", Colors.GREY
            )
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
        print(
            colored(
                f"Loaded {len(messages)} messages from conversation #{conversation_id}",
                Colors.GREY,
            )
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

                    print(colored("Assistant: ", Colors.BLUE), end="")
                    stream = ollama.chat(model=model_name, messages=msgs, stream=True)
                    return handle_ollama_stream(stream)
                else:
                    print(colored("Assistant: ", Colors.BLUE), end="")
                    print(msg["content"])
                    return msg["content"]
            else:
                print(colored("Assistant: ", Colors.BLUE), end="")
                stream = ollama.chat(model=model_name, messages=msgs, stream=True)
                return handle_ollama_stream(stream)
        except Exception as e:
            print_error(f"Error: {e}")
            return None

    # Handle Initial Prompt
    if initial_prompt or initial_images:
        if not initial_prompt:
            initial_prompt = "Describe this image."

        print(colored(f"🤖 [{model_name}] Thinking...", Colors.CYAN))

        user_message = {
            "role": "user",
            "content": initial_prompt,
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
            try:
                user_input = pt_prompt(
                    HTML("<ansigreen>You: </ansigreen>"), key_bindings=kb
                )
            except Exception:
                # Fallback to regular input if prompt_toolkit fails
                # print_warning(f"Prompt toolkit failed ({e}), falling back to standard input.") # Optional: debug
                user_input = input(colored("\nYou: ", Colors.GREEN))

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

            if cmd_root == "/reload-yolo":
                yolo_mode.reload_config()
                continue

            if cmd_root in ["/clear", "/cleat"]: # Handle typo from user request
                messages = []
                conversation_id = db.create_conversation(model_name)
                print(colored("\n🧹 Conversation cleared. Started new session.", Colors.GREEN))
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
                        print(colored("↩️  Undid last turn.", Colors.GREEN))
                    else:
                        print(colored("⚠️  Could not undo in database (maybe sync issue).", Colors.YELLOW))
                else:
                    print(colored("⚠️  Nothing to undo.", Colors.YELLOW))
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
                    print(colored(f"💾 Saved conversation to {filename}", Colors.GREEN))
                except Exception as e:
                    print_error(f"Failed to save: {e}")
                continue

            if cmd_root == "/run":
                if not cmd_arg:
                    print_warning("Usage: /run <command>")
                    continue
                print(colored(f"💻 Executing: {cmd_arg}", Colors.CYAN))
                result = tools.run_shell_command(cmd_arg)
                print(result)
                continue

            if cmd_root == "/explain":
                prompt_text = prompts_manager.get_prompt("explain")
                if prompt_text:
                    print(colored("🔍 Asking for explanation...", Colors.CYAN))
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
                    print(colored(f"🎭 Applied role: {cmd_arg}", Colors.GREEN))
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
                model_name = cmd_arg
                db.set_active_model(model_name)
                print(colored(f"🤖 Switched to model: {model_name}", Colors.GREEN))
                continue

            if cmd_root == "/search":
                if not cmd_arg:
                    print_warning("Usage: /search <query>")
                    continue
                print(colored(f"🌐 Searching web for: {cmd_arg}", Colors.CYAN))
                # Instruct the AI to use its tool capabilities (fetch_url, etc)
                # We format this as a user message to drive the agent
                user_input = f"Search the web for '{cmd_arg}' and provide a summary of the findings."
                # Proceed to normal processing which will treat this as the user prompt

            
            # TODO: Add /temp implementation if we want to pass options to ollama.chat

            print(colored(f"🤖 [{model_name}] Thinking...", Colors.CYAN))

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
            print(colored("\nChat session interrupted.", Colors.YELLOW))
            break
        except Exception as e:
            print()
            print_error(f"Error: {e}")
            if messages and messages[-1]["role"] == "user":
                messages.pop()

    # Stop hotkey listener when chat ends
    # yolo_mode.stop_hotkey_listener()
