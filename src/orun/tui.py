import json
import os

import ollama
from rich.markdown import Markdown
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static

from orun import db, prompts_manager, tools
from orun.yolo import yolo_mode


class ChatMessage(Static):
    """A widget to display a single chat message."""

    def __init__(self, role: str, content: str, **kwargs):
        super().__init__(**kwargs)
        self.role = role
        self.content_text = content
        # Basic styling based on role
        if role == "user":
            self.styles.background = "#223322"
            self.styles.margin = (1, 1, 1, 5)
            prefix = "**You:** "
        elif role == "assistant":
            self.styles.background = "#111133"
            self.styles.margin = (1, 5, 1, 1)
            prefix = "**AI:** "
        elif role == "tool":
            self.styles.background = "#333333"
            self.styles.color = "#aaaaaa"
            prefix = "🛠️ **Tool:** "
        else:
            prefix = f"**{role}:** "

        self.update(Markdown(prefix + content))

    def append_content(self, text: str):
        self.content_text += text
        prefix = (
            "**AI:** " if self.role == "assistant" else ""
        )  # Usually only append to assistant
        self.update(Markdown(prefix + self.content_text))


class ChatScreen(Screen):
    BINDINGS = [
        Binding("ctrl+l", "clear_screen", "Clear"),
    ]

    def __init__(
        self,
        model_name: str,
        conversation_id: int | None = None,
        initial_prompt: str | None = None,
        initial_images: list | None = None,
        use_tools: bool = False,
        yolo: bool = False,
        initial_prompt_template: str | None = None,
        initial_strategy_template: str | None = None,
    ):
        super().__init__()
        self.model_name = model_name
        self.conversation_id = conversation_id
        self.initial_prompt = initial_prompt
        self.initial_images = initial_images
        self.use_tools = use_tools
        self.initial_prompt_template = initial_prompt_template
        self.initial_strategy_template = initial_strategy_template

        if yolo:
            yolo_mode.yolo_active = True

        self.messages = []
        self.history_loaded = False

        if self.conversation_id:
            # Defer loading until mount so we can add widgets
            pass
        else:
            self.conversation_id = db.create_conversation(self.model_name)

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="chat_container")
        yield Input(placeholder="Type a message... ('/.' for commands)", id="chat_input")
        yield Footer()

    def on_mount(self) -> None:
        self.chat_container = self.query_one("#chat_container", VerticalScroll)
        self.input_widget = self.query_one("#chat_input", Input)
        self.title = f"Orun - {self.model_name}"

        # Load history
        if self.conversation_id and not self.history_loaded:
            history = db.get_conversation_messages(self.conversation_id)
            if history:
                self.chat_container.mount(
                    Static(
                        f"[dim]Loaded {len(history)} messages.[/dim]", classes="status"
                    )
                )
                for msg in history:
                    self.mount_message(msg["role"], msg["content"])
                    self.messages.append(msg)
            self.history_loaded = True

        self.input_widget.focus()
        self.update_yolo_status()

        # Handle Initial Prompt Logic
        if (
            self.initial_prompt
            or self.initial_images
            or self.initial_prompt_template
            or self.initial_strategy_template
        ):
            # Construct full prompt
            full_prompt = self.initial_prompt if self.initial_prompt else ""
            if not full_prompt and self.initial_images:
                full_prompt = "Describe this image."

            if self.initial_prompt_template:
                template = prompts_manager.get_prompt(self.initial_prompt_template)
                if template:
                    full_prompt = (
                        f"{template}\n\n{full_prompt}" if full_prompt else template
                    )
                else:
                    self.chat_container.mount(
                        Static(
                            f"[red]Prompt template '{self.initial_prompt_template}' not found[/]",
                            classes="status",
                        )
                    )

            if self.initial_strategy_template:
                template = prompts_manager.get_strategy(self.initial_strategy_template)
                if template:
                    full_prompt = (
                        f"{full_prompt}\n\n{template}" if full_prompt else template
                    )
                else:
                    self.chat_container.mount(
                        Static(
                            f"[red]Strategy template '{self.initial_strategy_template}' not found[/]",
                            classes="status",
                        )
                    )

            if full_prompt:
                self.input_widget.value = full_prompt
                self.input_widget.action_submit()

    def mount_message(self, role: str, content: str) -> ChatMessage:
        msg_widget = ChatMessage(role, content)
        self.chat_container.mount(msg_widget)
        msg_widget.scroll_visible()
        return msg_widget

    def get_command_entries(self) -> list[tuple[str, str]]:
        """Available slash commands and their descriptions."""
        return [
            ("/.", "Show available commands"),
            ("/clear", "Start a fresh conversation"),
            ("/model [alias]", "Show or switch model (starts fresh convo on change)"),
            ("/reload", "Reload model list from Ollama"),
            ("/run <cmd>", "Run a shell command (respecting whitelist/YOLO)"),
        ]

    def show_command_list(self) -> None:
        lines = ["[cyan]Commands:[/cyan]"]
        for name, desc in self.get_command_entries():
            lines.append(f"  [green]{name}[/green] - {desc}")
        self.chat_container.mount(Static("\n".join(lines), classes="status"))
        self.chat_container.scroll_end()

    def action_toggle_yolo(self) -> None:
        yolo_mode.toggle(show_message=False)
        self.update_yolo_status()
        status = "ENABLED" if yolo_mode.yolo_active else "DISABLED"
        color = "red" if yolo_mode.yolo_active else "green"
        self.chat_container.mount(
            Static(f"[{color}]🔥 YOLO MODE {status}[/]", classes="status")
        )
        self.chat_container.scroll_end()

    def update_yolo_status(self) -> None:
        self.sub_title = "🔥 YOLO MODE" if yolo_mode.yolo_active else "✅ Safe Mode"

    def action_clear_screen(self) -> None:
        # We can't easily clear widgets in Textual safely without awaiting remove(),
        # simpler to just start a new conversation logically.
        self.messages = []
        self.conversation_id = db.create_conversation(self.model_name)
        # Remove all children?
        self.chat_container.remove_children()
        self.chat_container.mount(
            Static("[green]🧹 Conversation cleared.[/]", classes="status")
        )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_input = event.value.strip()
        if not user_input:
            return

        self.input_widget.value = ""
        self.input_widget.disabled = True  # Disable input while processing

        # Handle Local Commands
        if user_input.startswith("/"):
            await self.handle_slash_command(user_input)
            self.input_widget.disabled = False
            self.input_widget.focus()
            return

        # Show User Message
        self.mount_message("user", user_input)
        self.messages.append({"role": "user", "content": user_input})
        db.add_message(self.conversation_id, "user", user_input)

        # Start AI Processing
        self.process_ollama_turn()

    async def handle_slash_command(self, text: str) -> None:
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/yolo":
            self.action_toggle_yolo()
        elif cmd == "/clear":
            self.action_clear_screen()
        elif cmd == "/run":
            self.chat_container.mount(
                Static(f"[cyan]💻 Executing: {arg}[/]", classes="status")
            )
            self.chat_container.scroll_end()
            result = tools.run_shell_command(arg)
            self.chat_container.mount(Static(result, classes="status"))
        else:
            self.chat_container.mount(
                Static(f"[yellow]Unknown command: {cmd}[/]", classes="status")
            )

        self.chat_container.scroll_end()

    @work(exclusive=True, thread=True)
    def process_ollama_turn(self) -> None:
        try:
            tool_defs = tools.TOOL_DEFINITIONS if self.use_tools else None

            # Step 1: Initial Call (Sync)
            # If using tools, we assume we might get tool calls first (not streamed)
            # OR we can stream and parse? Ollama python lib `stream=True` yields chunks.
            # If `tools` is passed, Ollama usually returns one non-streamed response with tool_calls
            # OR a stream where one chunk contains them.
            # Safest is `stream=False` for the first hop if using tools.

            if self.use_tools:
                response = ollama.chat(
                    model=self.model_name,
                    messages=self.messages,
                    tools=tool_defs,
                    stream=False,
                )
                msg = response["message"]
                self.messages.append(msg)

                if msg.get("tool_calls"):
                    # Handle Tools
                    for tool in msg["tool_calls"]:
                        fn = tool.function.name
                        args = tool.function.arguments
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except:
                                pass

                        # Display Tool Usage
                        self.app.call_from_thread(
                            self.chat_container.mount,
                            Static(
                                f"[magenta]🛠️  Calling: {fn}({args})[/]",
                                classes="status",
                            ),
                        )

                        # Execute (Permission check simplified to YOLO or Allow)
                        allowed = True
                        if fn == "run_shell_command" and "command" in args:
                            skip, reason = yolo_mode.should_skip_confirmation(
                                args["command"]
                            )
                            if not skip:
                                # For TUI v1, we block execution if not YOLO/White.
                                # Implementing modal confirmation is complex.
                                self.app.call_from_thread(
                                    self.chat_container.mount,
                                    Static(
                                        f"[red]❌ Blocked: {reason} (Enable YOLO to bypass)[/]",
                                        classes="status",
                                    ),
                                )
                                allowed = False

                        if allowed:
                            func_impl = tools.AVAILABLE_TOOLS.get(fn)
                            if func_impl:
                                try:
                                    res = func_impl(**args)
                                    self.messages.append(
                                        {"role": "tool", "content": str(res)}
                                    )
                                    self.app.call_from_thread(
                                        self.chat_container.mount,
                                        Static(
                                            f"[dim]Result: {str(res)[:200]}...[/]",
                                            classes="status",
                                        ),
                                    )
                                except Exception as e:
                                    self.messages.append(
                                        {"role": "tool", "content": f"Error: {e}"}
                                    )
                            else:
                                self.messages.append(
                                    {"role": "tool", "content": "Tool not found"}
                                )

                    # After tools, get final response (Streamed)
                    self.stream_assistant_response()
                else:
                    # No tools, just content.
                    # But since we used stream=False, we have the full content already.
                    content = msg["content"]
                    self.app.call_from_thread(self.mount_message, "assistant", content)
                    db.add_message(self.conversation_id, "assistant", content)

            else:
                # No tools, just stream directly
                self.stream_assistant_response()

        except Exception as e:
            self.app.call_from_thread(
                self.chat_container.mount,
                Static(f"[red]Error: {e}[/]", classes="status"),
            )
        finally:
            self.app.call_from_thread(self.enable_input)

    def stream_assistant_response(self):
        # Create the widget on the main thread
        widget = ChatMessage("assistant", "")
        self.app.call_from_thread(self.chat_container.mount, widget)
        self.app.call_from_thread(widget.scroll_visible)

        full_resp = ""
        stream = ollama.chat(model=self.model_name, messages=self.messages, stream=True)

        for chunk in stream:
            content = chunk["message"]["content"]
            full_resp += content
            # Update widget on main thread
            self.app.call_from_thread(widget.append_content, content)
            # Force scroll to bottom occasionally? Textual might auto-scroll if we use `scroll_end`?
            # self.app.call_from_thread(self.chat_container.scroll_end)

        self.messages.append({"role": "assistant", "content": full_resp})
        db.add_message(self.conversation_id, "assistant", full_resp)

    def enable_input(self):
        self.input_widget.disabled = False
        self.input_widget.focus()


class OrunApp(App):
    CSS = """
    #chat_container {
        height: 1fr;
        padding: 1;
    }
    #chat_input {
        dock: bottom;
        border: wide $accent;
    }
    .status {
        color: $text-muted;
        padding-left: 1;
    }
    ChatMessage {
        padding: 1;
        margin-bottom: 1;
        background: $panel;
        border-left: wide $primary;
    }
    """

    def __init__(self, **kwargs):
        self.chat_args = kwargs
        super().__init__()

    def on_mount(self) -> None:
        self.push_screen(ChatScreen(**self.chat_args))
