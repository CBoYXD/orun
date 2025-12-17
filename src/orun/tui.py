import asyncio
import json

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

SEARCH_ANALYSIS_PROMPT_NAME = "search_analysis"
HIDDEN_ROLE_MAP = {"hidden_user": "user"}
HIDDEN_ROLES = set(HIDDEN_ROLE_MAP.keys())
DEFAULT_SEARCH_ANALYSIS_PROMPT = (
    "You are Orun's search analyst. Given the fetched document, produce a concise yet"
    " detailed analysis:\n"
    "- Start with a short overview mentioning the source.\n"
    "- List the most important facts or claims.\n"
    "- Highlight potential risks, opportunities, and recommended next steps.\n"
    "- Call out gaps or uncertainties if the content is limited.\n"
    "Keep the tone analytical and practical."
)


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
        self.active_prompt_template = None
        self.active_strategy_template = None

        if yolo:
            yolo_mode.yolo_active = True

        self.messages = []
        self.command_hint_shown = False
        self.history_loaded = False
        self.command_hint_widget = None

        self.search_analysis_prompt = (
            prompts_manager.get_prompt(SEARCH_ANALYSIS_PROMPT_NAME)
            or DEFAULT_SEARCH_ANALYSIS_PROMPT
        )

        if self.conversation_id:
            # Defer loading until mount so we can add widgets
            pass
        else:
            self.conversation_id = db.create_conversation(self.model_name)

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="chat_container")
        yield Input(placeholder="Type a message... ('/' for commands)", id="chat_input")
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
                    stored_role = msg["role"]
                    content = msg["content"]
                    effective_role = HIDDEN_ROLE_MAP.get(stored_role, stored_role)
                    if stored_role not in HIDDEN_ROLES:
                        self.mount_message(stored_role, content)
                    self.messages.append({"role": effective_role, "content": content})
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

    def build_user_payload(self, user_input: str) -> str:
        prompt_name = self.active_prompt_template
        strategy_name = self.active_strategy_template
        if not prompt_name and not strategy_name:
            return user_input

        build = prompts_manager.compose_prompt(
            user_prompt=user_input,
            prompt_template=prompt_name,
            strategy_template=strategy_name,
        )
        for missing in build.missing:
            self.chat_container.mount(
                Static(f"[yellow]Template {missing} not found.[/]", classes="status")
            )
        return build.text or user_input

    def get_command_entries(self) -> list[tuple[str, str]]:
        """Available slash commands and their descriptions."""
        return [
            ("/run <cmd>", "Run a shell command"),
            ("/search <url>", "Fetch and summarize a web page"),
            ("/prompt <name>", "Set/list prompt templates"),
            ("/strategy <name>", "Set/list strategy templates"),
            ("/model [alias]", "Show or switch the active model"),
            ("/reload", "Reload model list from Ollama"),
        ]

    def hide_command_list(self) -> None:
        if self.command_hint_widget and self.command_hint_widget.parent:
            self.command_hint_widget.remove()
        self.command_hint_widget = None
        self.command_hint_shown = False

    def show_command_list(self) -> None:
        lines = ["[cyan]Commands:[/cyan]"]
        for name, desc in self.get_command_entries():
            lines.append(f"  [green]{name}[/green] - {desc}")
        self.hide_command_list()
        self.command_hint_widget = Static("\n".join(lines), classes="status")
        self.chat_container.mount(self.command_hint_widget)
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

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "chat_input":
            return

        value = event.value.strip()
        if value == "/":
            if not self.command_hint_shown:
                self.show_command_list()
                self.command_hint_shown = True
        else:
            self.hide_command_list()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_input = event.value.strip()
        if not user_input:
            return

        self.hide_command_list()
        self.input_widget.value = ""
        self.input_widget.disabled = True  # Disable input while processing

        # Handle Local Commands
        if user_input.startswith("/"):
            wait_for_ai = await self.handle_slash_command(user_input)
            if not wait_for_ai:
                self.input_widget.disabled = False
                self.input_widget.focus()
            return

        # Build final payload (including active templates) & show user message
        payload = self.build_user_payload(user_input)
        self.mount_message("user", user_input)
        self.messages.append({"role": "user", "content": payload})
        db.add_message(self.conversation_id, "user", payload)

        # Start AI Processing
        self.process_ollama_turn()

    async def handle_slash_command(self, text: str) -> bool:
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        trigger_model = False

        if cmd == "/yolo":
            self.action_toggle_yolo()
        elif cmd == "/clear":
            self.action_clear_screen()
        elif cmd == "/run":
            if not arg:
                self.chat_container.mount(
                    Static("[yellow]Usage: /run <command>[/]", classes="status")
                )
            else:
                self.chat_container.mount(
                    Static(f"[cyan]💻 Executing: {arg}[/]", classes="status")
                )
                self.chat_container.scroll_end()
                result = await asyncio.to_thread(tools.run_shell_command, arg)
                self.chat_container.mount(
                    Static(result or "[dim](no output)[/]", classes="status")
                )
        elif cmd == "/search":
            if not arg:
                self.chat_container.mount(
                    Static("[yellow]Usage: /search <url>[/]", classes="status")
                )
            else:
                url = arg.strip()
                if not url.startswith(("http://", "https://")):
                    url = f"https://{url}"
                self.chat_container.mount(
                    Static(f"[cyan]Fetching {url} ...[/]", classes="status")
                )
                self.chat_container.scroll_end()
                result = await asyncio.to_thread(tools.fetch_url, url)
                result_trimmed = result.strip()
                if result_trimmed.lower().startswith("error"):
                    self.chat_container.mount(
                        Static(result_trimmed, classes="status")
                    )
                else:
                    self.chat_container.mount(
                        Static("[cyan]Content fetched. Asking AI to analyze...[/]", classes="status")
                    )
                    analysis_payload = (
                        f"{self.search_analysis_prompt}\n\n"
                        f"Source URL: {url}\n\n"
                        "-----BEGIN DOCUMENT-----\n"
                        f"{result_trimmed}\n"
                        "-----END DOCUMENT-----"
                    )
                    self.messages.append({"role": "user", "content": analysis_payload})
                    db.add_message(
                        self.conversation_id, "hidden_user", analysis_payload
                    )
                    trigger_model = True
                    self.process_ollama_turn()
        elif cmd == "/prompt":
            sub = arg.strip()
            sub_lower = sub.lower()
            if not sub or sub_lower in {"list", "ls"}:
                prompts = await asyncio.to_thread(prompts_manager.list_prompts)
                if not prompts:
                    self.chat_container.mount(
                        Static("[yellow]No prompts found.[/]", classes="status")
                    )
                else:
                    lines = ["[cyan]Available Prompts:[/cyan]"]
                    preview = prompts[:25]
                    for name in preview:
                        lines.append(f"  [green]{name}[/green]")
                    if len(prompts) > len(preview):
                        lines.append(f"... ({len(prompts) - len(preview)} more)")
                    current = (
                        f"[dim]Current: {self.active_prompt_template}[/]"
                        if self.active_prompt_template
                        else "[dim]Current: (none)[/]"
                    )
                    lines.append(current)
                    self.chat_container.mount(Static("\n".join(lines), classes="status"))
            elif sub_lower in {"clear", "none"}:
                self.active_prompt_template = None
                self.chat_container.mount(
                    Static("[green]Prompt template cleared.[/]", classes="status")
                )
            else:
                content = await asyncio.to_thread(prompts_manager.get_prompt, sub)
                if not content:
                    self.chat_container.mount(
                        Static(
                            f"[yellow]Prompt '{sub}' not found.[/]",
                            classes="status",
                        )
                    )
                else:
                    self.active_prompt_template = sub
                    self.chat_container.mount(
                        Static(
                            f"[green]Prompt '{sub}' activated ({len(content)} chars).[/]",
                            classes="status",
                        )
                    )
        elif cmd == "/strategy":
            sub = arg.strip()
            sub_lower = sub.lower()
            if not sub or sub_lower in {"list", "ls"}:
                strategies = await asyncio.to_thread(prompts_manager.list_strategies)
                if not strategies:
                    self.chat_container.mount(
                        Static("[yellow]No strategies found.[/]", classes="status")
                    )
                else:
                    lines = ["[cyan]Available Strategies:[/cyan]"]
                    preview = strategies[:25]
                    for name in preview:
                        lines.append(f"  [green]{name}[/green]")
                    if len(strategies) > len(preview):
                        lines.append(
                            f"... ({len(strategies) - len(preview)} more)"
                        )
                    current = (
                        f"[dim]Current: {self.active_strategy_template}[/]"
                        if self.active_strategy_template
                        else "[dim]Current: (none)[/]"
                    )
                    lines.append(current)
                    self.chat_container.mount(Static("\n".join(lines), classes="status"))
            elif sub_lower in {"clear", "none"}:
                self.active_strategy_template = None
                self.chat_container.mount(
                    Static("[green]Strategy template cleared.[/]", classes="status")
                )
            else:
                content = await asyncio.to_thread(prompts_manager.get_strategy, sub)
                if not content:
                    self.chat_container.mount(
                        Static(
                            f"[yellow]Strategy '{sub}' not found.[/]",
                            classes="status",
                        )
                    )
                else:
                    self.active_strategy_template = sub
                    self.chat_container.mount(
                        Static(
                            f"[green]Strategy '{sub}' activated ({len(content)} chars).[/]",
                            classes="status",
                        )
                    )
        elif cmd == "/model":
            if not arg:
                models = await asyncio.to_thread(db.get_models)
                active = await asyncio.to_thread(db.get_active_model)
                if not models:
                    self.chat_container.mount(
                        Static(
                            "[yellow]No models found. Use /reload to sync from Ollama.[/]",
                            classes="status",
                        )
                    )
                else:
                    lines = ["[cyan]Available Models:[/cyan]"]
                    for alias, name in sorted(models.items()):
                        marker = " [green](active)[/]" if name == active else ""
                        lines.append(f"  [green]{alias}[/green] -> {name}{marker}")
                    self.chat_container.mount(Static("\n".join(lines), classes="status"))
            else:
                switched = await asyncio.to_thread(db.set_active_model, arg)
                if not switched:
                    self.chat_container.mount(
                        Static(f"[red]Model '{arg}' not found.[/]", classes="status")
                    )
                else:
                    new_model = await asyncio.to_thread(db.get_active_model)
                    self.model_name = new_model or arg
                    self.title = f"Orun - {self.model_name}"
                    self.messages = []
                    self.conversation_id = db.create_conversation(self.model_name)
                    self.chat_container.remove_children()
                    self.chat_container.mount(
                        Static(
                            f"[green]Switched to {self.model_name}. Started a new conversation.[/]",
                            classes="status",
                        )
                    )
        elif cmd == "/reload":
            self.chat_container.mount(
                Static("[cyan]Reloading models from Ollama...[/]", classes="status")
            )
            self.chat_container.scroll_end()
            try:
                await asyncio.to_thread(db.refresh_ollama_models)
                self.chat_container.mount(
                    Static("[green]Model list reloaded.[/]", classes="status")
                )
            except Exception as exc:
                self.chat_container.mount(
                    Static(f"[red]Reload failed: {exc}[/]", classes="status")
                )
        else:
            self.chat_container.mount(
                Static(f"[yellow]Unknown command: {cmd}[/]", classes="status")
            )

        self.chat_container.scroll_end()
        return trigger_model

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
