import asyncio
import json
import os
import traceback

import ollama
from rich.markdown import Markdown
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static

from orun import db, prompts_manager, tools, utils
from orun.consensus_config import consensus_config
from orun.models_config import models_config
from orun.yolo import yolo_mode

SEARCH_ANALYSIS_PROMPT_NAME = "search_analysis"
ARXIV_ANALYSIS_PROMPT_NAME = "arxiv_analysis"
HIDDEN_ROLE_MAP = {"hidden_user": "user"}
HIDDEN_ROLES = set(HIDDEN_ROLE_MAP.keys())
LIST_PAGE_SIZE = 25


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
        Binding("left", "template_page_prev", "", show=False, priority=True),
        Binding("right", "template_page_next", "", show=False, priority=True),
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
        self.active_prompt_templates: list[str] = (
            [initial_prompt_template] if initial_prompt_template else []
        )
        self.active_strategy_template = initial_strategy_template

        if yolo:
            yolo_mode.yolo_active = True

        self.messages = []
        self.command_hint_shown = False
        self.history_loaded = False
        self.command_hint_widget = None
        self.template_list_state = None
        self.template_list_widget = None
        self.pending_images = []
        self.pending_files = []
        self.pending_dir_context = None
        self.pending_clipboard_text = None
        self.system_prompt = None
        self.model_options = {}

        self.search_analysis_prompt = prompts_manager.get_prompt(
            SEARCH_ANALYSIS_PROMPT_NAME
        )
        self.arxiv_analysis_prompt = prompts_manager.get_prompt(
            ARXIV_ANALYSIS_PROMPT_NAME
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
                        display = self.display_content_for(stored_role, content)
                        self.mount_message(stored_role, display)
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

    def display_content_for(self, role: str, content: str) -> str:
        if role == "user":
            return self._format_user_display(content)
        return content

    def _format_user_display(self, content: str) -> str:
        if not content:
            return content
        newline_count = content.count("\n")
        char_count = len(content)
        line_count = newline_count + 1 if content else 0
        if newline_count >= 4 or char_count > 800:
            return f"Paste Lines[{line_count}]"
        return content

    def parse_page_argument(self, raw: str) -> tuple[int, str | None]:
        if not raw:
            return 1, None
        try:
            page = max(1, int(raw))
            return page, None
        except ValueError:
            return 1, f"[yellow]Invalid page '{raw}'. Showing page 1.[/]"

    def show_template_list(
        self,
        items: list[str],
        page: int,
        label: str,
        current_line: str | None = None,
        store_state: bool = False,
    ) -> None:
        if not items:
            self.chat_container.mount(
                Static(f"[yellow]No {label.lower()} found.[/]", classes="status")
            )
            return

        total = len(items)
        total_pages = max(1, (total + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE)
        page = min(page, total_pages)
        start = (page - 1) * LIST_PAGE_SIZE
        end = start + LIST_PAGE_SIZE
        slice_items = items[start:end]

        lines = [
            f"[cyan]{label}[/cyan]",
            f"[dim]Page {page}/{total_pages} (total {total})[/]",
        ]
        for name in slice_items:
            lines.append(f"  [green]{name}[/green]")
        if total_pages > 1:
            lines.append("[dim]Use ←/→ to change page[/]")
        if current_line:
            lines.append(current_line)

        if self.template_list_widget and self.template_list_widget.parent:
            self.template_list_widget.remove()
        widget = Static("\n".join(lines), classes="status")
        self.template_list_widget = widget
        self.chat_container.mount(widget)
        self.chat_container.scroll_end()

        if store_state:
            self.template_list_state = {
                "items": items,
                "label": label,
                "current_line": current_line,
                "page": page,
            }
        elif self.template_list_state:
            self.template_list_state["page"] = page

    def build_user_payload(self, user_input: str) -> str:
        prompt_names = self.active_prompt_templates
        strategy_name = self.active_strategy_template

        parts: list[str] = []

        # Add clipboard text if available
        if self.pending_clipboard_text:
            parts.append(f"--- Input from clipboard ---\n{self.pending_clipboard_text}")

        # Add directory context if available
        if self.pending_dir_context:
            parts.append(self.pending_dir_context)

        # Add file context if available
        if self.pending_files:
            file_context = utils.read_file_context(self.pending_files)
            if file_context:
                parts.append(file_context)

        # Add prompt templates
        for name in prompt_names:
            prompt_text = prompts_manager.get_prompt(name)
            if prompt_text:
                parts.append(prompt_text.strip())
            else:
                self.chat_container.mount(
                    Static(
                        f"[yellow]Template prompt '{name}' not found.[/]",
                        classes="status",
                    )
                )

        parts.append(user_input)

        if strategy_name:
            strategy_text = prompts_manager.get_strategy(strategy_name)
            if strategy_text:
                parts.append(strategy_text.strip())
            else:
                self.chat_container.mount(
                    Static(
                        f"[yellow]Template strategy '{strategy_name}' not found.[/]",
                        classes="status",
                    )
                )

        composed = "\n\n".join(part for part in parts if part.strip())
        return composed if composed.strip() else user_input

    def update_template_list_page(self, delta: int) -> None:
        state = self.template_list_state
        if not state:
            return
        items = state["items"]
        label = state["label"]
        current_line = state["current_line"]
        page = state["page"] + delta
        total = len(items)
        total_pages = max(1, (total + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE)
        page = max(1, min(total_pages, page))
        if page == state["page"]:
            return
        self.show_template_list(items, page, label, current_line)

    def action_template_page_prev(self) -> None:
        if self.template_list_state:
            self.update_template_list_page(-1)

    def action_template_page_next(self) -> None:
        if self.template_list_state:
            self.update_template_list_page(1)

    def get_command_entries(self) -> list[tuple[str, str]]:
        """Available slash commands and their descriptions."""
        return [
            ("/run <cmd>", "Run a shell command"),
            ("/search <query>", "Search the web (Google/DuckDuckGo)"),
            ("/fetch <url>", "Fetch and parse a web page"),
            ("/arxiv <query|id>", "Search arXiv or get paper details"),
            ("/image [indices]", "Attach screenshots (e.g., '1', '1,2', '3x')"),
            ("/paste", "Paste image from clipboard"),
            ("/file <paths...>", "Add files as context (supports globs)"),
            ("/dir <path>", "Scan directory and add as context"),
            ("/clipboard", "Paste text from clipboard"),
            ("/system <prompt>", "Set custom system prompt"),
            ("/temperature <value>", "Set model temperature (0.0-2.0)"),
            ("/topp <value>", "Set top-p sampling (0.0-1.0)"),
            ("/export <path>", "Save conversation to file"),
            ("/prompt <name...>", "Activate prompt templates"),
            ("/prompt remove <name>", "Remove a prompt template"),
            ("/prompts [page|active]", "List available/active prompt templates"),
            ("/strategy <name>", "Activate or clear strategy template"),
            ("/strategies [page]", "List available strategy templates"),
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

    def clear_template_list_state(self) -> None:
        self.template_list_state = None
        if self.template_list_widget and self.template_list_widget.parent:
            self.template_list_widget.remove()
        self.template_list_widget = None

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

    @work(exclusive=False, thread=True)
    def run_paste_worker(self) -> None:
        """Worker thread for paste operation"""
        try:
            # Try to get an image from clipboard
            image_path = utils.save_clipboard_image()

            if image_path:
                # Image found - add to pending
                self.pending_images.append(image_path)
                self.app.call_from_thread(
                    self.chat_container.mount,
                    Static(
                        f"[green]📋 Clipboard image added to pending[/]\n🖼️  {os.path.basename(image_path)}",
                        classes="status",
                    ),
                )
                self.app.call_from_thread(self.chat_container.scroll_end)
            else:
                # No image found
                self.app.call_from_thread(
                    self.chat_container.mount,
                    Static("[yellow]No image found in clipboard[/]", classes="status"),
                )
                self.app.call_from_thread(self.chat_container.scroll_end)
        except Exception as e:
            error_details = traceback.format_exc()
            self.app.call_from_thread(
                self.chat_container.mount,
                Static(
                    f"[red]Error pasting from clipboard: {e}[/]\n[dim]{error_details}[/]",
                    classes="status",
                ),
            )
            self.app.call_from_thread(self.chat_container.scroll_end)

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
            if value and not value.startswith("/"):
                self.clear_template_list_state()

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
        display_text = self.display_content_for("user", user_input)
        self.mount_message("user", display_text)

        # Attach pending images if any
        images_to_attach = self.pending_images if self.pending_images else None
        if images_to_attach:
            # Show which images are being attached
            image_names = [os.path.basename(img) for img in images_to_attach]
            self.chat_container.mount(
                Static(
                    f"[dim]📎 Attached {len(images_to_attach)} image(s): {', '.join(image_names)}[/]",
                    classes="status",
                )
            )
            self.messages.append(
                {"role": "user", "content": payload, "images": images_to_attach}
            )
            db.add_message(self.conversation_id, "user", payload, images_to_attach)
            # Clear pending images after attaching
            self.pending_images = []
        else:
            self.messages.append({"role": "user", "content": payload})
            db.add_message(self.conversation_id, "user", payload)

        # Clear pending context after using
        self.pending_files = []
        self.pending_dir_context = None
        self.pending_clipboard_text = None

        # Start AI Processing
        self.process_ollama_turn()

    async def handle_slash_command(self, text: str) -> bool:
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        trigger_model = False

        if cmd not in {"/prompts", "/strategies"}:
            self.clear_template_list_state()

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
                    Static("[yellow]Usage: /search <query>[/]", classes="status")
                )
            else:
                query = arg.strip()
                self.chat_container.mount(
                    Static(
                        f"[cyan]Searching the web for '{query}'...[/]", classes="status"
                    )
                )
                self.chat_container.scroll_end()
                result = await asyncio.to_thread(tools.web_search, query, 5)
                result_trimmed = result.strip()
                if result_trimmed.lower().startswith("error"):
                    self.chat_container.mount(Static(result_trimmed, classes="status"))
                else:
                    self.chat_container.mount(
                        Static(
                            "[cyan]Search results fetched. Asking AI to analyze...[/]",
                            classes="status",
                        )
                    )
                    analysis_payload = (
                        f"{self.search_analysis_prompt}\n\n"
                        f"Search Query: {query}\n\n"
                        "-----BEGIN SEARCH RESULTS-----\n"
                        f"{result_trimmed}\n"
                        "-----END SEARCH RESULTS-----"
                    )
                    self.messages.append({"role": "user", "content": analysis_payload})
                    db.add_message(
                        self.conversation_id, "hidden_user", analysis_payload
                    )
                    trigger_model = True
                    self.process_ollama_turn()
        elif cmd == "/fetch":
            if not arg:
                self.chat_container.mount(
                    Static("[yellow]Usage: /fetch <url>[/]", classes="status")
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
                    self.chat_container.mount(Static(result_trimmed, classes="status"))
                else:
                    self.chat_container.mount(
                        Static(
                            "[cyan]Content fetched. Asking AI to analyze...[/]",
                            classes="status",
                        )
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
        elif cmd == "/arxiv":
            if not arg:
                self.chat_container.mount(
                    Static(
                        "[yellow]Usage: /arxiv <query or arxiv_id>[/]", classes="status"
                    )
                )
            else:
                query = arg.strip()
                # Check if it looks like an arXiv ID (digits, dots, optional v)
                is_id = bool(
                    query.replace(".", "").replace("v", "").replace("/", "").isdigit()
                )

                if is_id or "arxiv.org" in query.lower():
                    # Get specific paper
                    self.chat_container.mount(
                        Static(
                            f"[cyan]Fetching arXiv paper {query}...[/]",
                            classes="status",
                        )
                    )
                    self.chat_container.scroll_end()
                    result = await asyncio.to_thread(tools.get_arxiv_paper, query)
                else:
                    # Search for papers
                    self.chat_container.mount(
                        Static(
                            f"[cyan]Searching arXiv for '{query}'...[/]",
                            classes="status",
                        )
                    )
                    self.chat_container.scroll_end()
                    result = await asyncio.to_thread(tools.search_arxiv, query, 5)

                result_trimmed = result.strip()
                if result_trimmed.lower().startswith("error"):
                    self.chat_container.mount(Static(result_trimmed, classes="status"))
                else:
                    self.chat_container.mount(
                        Static(
                            "[cyan]Paper(s) fetched. Asking AI to analyze...[/]",
                            classes="status",
                        )
                    )
                    analysis_payload = (
                        f"{self.arxiv_analysis_prompt}\n\n"
                        f"Query: {query}\n\n"
                        "-----BEGIN ARXIV DATA-----\n"
                        f"{result_trimmed}\n"
                        "-----END ARXIV DATA-----"
                    )
                    self.messages.append({"role": "user", "content": analysis_payload})
                    db.add_message(
                        self.conversation_id, "hidden_user", analysis_payload
                    )
                    trigger_model = True
                    self.process_ollama_turn()
        elif cmd == "/image":
            # Parse arguments like -i parameter (1, 1,2, 3x, or empty for latest)
            tokens = [tok for tok in arg.split() if tok]
            image_args = tokens if tokens else []

            # Get image paths using the same logic as -i parameter
            # Empty list [] means use latest image (index 1)
            try:
                new_images = await asyncio.to_thread(
                    utils.get_image_paths, image_args if image_args else []
                )
                if new_images:
                    self.pending_images.extend(new_images)
                    # Display confirmation
                    image_names = [f"🖼️  {os.path.basename(img)}" for img in new_images]
                    self.chat_container.mount(
                        Static(
                            f"[green]Images added to pending ({len(new_images)}):[/]\n"
                            + "\n".join(image_names),
                            classes="status",
                        )
                    )
                else:
                    self.chat_container.mount(
                        Static(
                            "[yellow]No images found matching the criteria.[/]",
                            classes="status",
                        )
                    )
            except Exception as e:
                self.chat_container.mount(
                    Static(f"[red]Error loading images: {e}[/]", classes="status")
                )
        elif cmd == "/paste":
            # Save image from clipboard
            try:
                image_path = await asyncio.to_thread(utils.save_clipboard_image)
                if image_path:
                    self.pending_images.append(image_path)
                    self.chat_container.mount(
                        Static(
                            f"[green]📋 Clipboard image added to pending[/]\n🖼️  {os.path.basename(image_path)}",
                            classes="status",
                        )
                    )
                else:
                    self.chat_container.mount(
                        Static(
                            "[yellow]No image found in clipboard[/]", classes="status"
                        )
                    )
            except Exception as e:
                self.chat_container.mount(
                    Static(
                        f"[red]Error pasting from clipboard: {e}[/]", classes="status"
                    )
                )
        elif cmd == "/file":
            # Add files as context (supports glob patterns)
            if not arg:
                self.chat_container.mount(
                    Static(
                        "[yellow]Usage: /file <path1> [path2...][/]", classes="status"
                    )
                )
            else:
                tokens = arg.split()
                try:
                    file_paths = await asyncio.to_thread(
                        utils.parse_file_patterns, tokens
                    )
                    if file_paths:
                        self.pending_files.extend(file_paths)
                        file_names = [f"📄 {os.path.basename(f)}" for f in file_paths]
                        self.chat_container.mount(
                            Static(
                                f"[green]Files added to context ({len(file_paths)}):[/]\n"
                                + "\n".join(file_names),
                                classes="status",
                            )
                        )
                    else:
                        self.chat_container.mount(
                            Static(
                                "[yellow]No files found matching the pattern.[/]",
                                classes="status",
                            )
                        )
                except Exception as e:
                    self.chat_container.mount(
                        Static(f"[red]Error loading files: {e}[/]", classes="status")
                    )
        elif cmd == "/dir":
            # Scan directory and add as context
            if not arg:
                self.chat_container.mount(
                    Static("[yellow]Usage: /dir <directory_path>[/]", classes="status")
                )
            else:
                dir_path = arg.strip()
                try:
                    self.chat_container.mount(
                        Static(
                            f"[cyan]Scanning directory: {dir_path}...[/]",
                            classes="status",
                        )
                    )
                    self.chat_container.scroll_end()
                    dir_context = await asyncio.to_thread(
                        utils.read_directory_context, dir_path
                    )
                    if dir_context:
                        self.pending_dir_context = dir_context
                        self.chat_container.mount(
                            Static(
                                f"[green]Directory context loaded ({len(dir_context)} chars)[/]",
                                classes="status",
                            )
                        )
                    else:
                        self.chat_container.mount(
                            Static(
                                "[yellow]No readable files found in directory.[/]",
                                classes="status",
                            )
                        )
                except Exception as e:
                    self.chat_container.mount(
                        Static(
                            f"[red]Error scanning directory: {e}[/]", classes="status"
                        )
                    )
        elif cmd == "/clipboard":
            # Paste text from clipboard
            try:
                clipboard_text = await asyncio.to_thread(utils.read_clipboard_text)
                if clipboard_text:
                    self.pending_clipboard_text = clipboard_text
                    preview = (
                        clipboard_text[:100] + "..."
                        if len(clipboard_text) > 100
                        else clipboard_text
                    )
                    self.chat_container.mount(
                        Static(
                            f"[green]📋 Clipboard text loaded ({len(clipboard_text)} chars)[/]\n[dim]{preview}[/]",
                            classes="status",
                        )
                    )
                else:
                    self.chat_container.mount(
                        Static(
                            "[yellow]No text found in clipboard[/]", classes="status"
                        )
                    )
            except Exception as e:
                self.chat_container.mount(
                    Static(f"[red]Error reading clipboard: {e}[/]", classes="status")
                )
        elif cmd == "/system":
            # Set custom system prompt
            if not arg:
                if self.system_prompt:
                    self.chat_container.mount(
                        Static(
                            f"[cyan]Current system prompt:[/]\n{self.system_prompt}",
                            classes="status",
                        )
                    )
                else:
                    self.chat_container.mount(
                        Static(
                            "[yellow]Usage: /system <prompt> | /system clear[/]",
                            classes="status",
                        )
                    )
            elif arg.strip().lower() == "clear":
                self.system_prompt = None
                self.chat_container.mount(
                    Static("[green]System prompt cleared.[/]", classes="status")
                )
            else:
                self.system_prompt = arg.strip()
                self.chat_container.mount(
                    Static(
                        f"[green]System prompt set ({len(self.system_prompt)} chars)[/]",
                        classes="status",
                    )
                )
        elif cmd == "/temperature":
            # Set model temperature
            if not arg:
                current = self.model_options.get("temperature", "not set")
                self.chat_container.mount(
                    Static(f"[cyan]Current temperature: {current}[/]", classes="status")
                )
            else:
                try:
                    value = float(arg.strip())
                    if 0.0 <= value <= 2.0:
                        self.model_options["temperature"] = value
                        self.chat_container.mount(
                            Static(
                                f"[green]Temperature set to {value}[/]",
                                classes="status",
                            )
                        )
                    else:
                        self.chat_container.mount(
                            Static(
                                "[yellow]Temperature must be between 0.0 and 2.0[/]",
                                classes="status",
                            )
                        )
                except ValueError:
                    self.chat_container.mount(
                        Static(
                            "[yellow]Invalid temperature value. Use a number between 0.0 and 2.0[/]",
                            classes="status",
                        )
                    )
        elif cmd == "/topp":
            # Set top-p sampling
            if not arg:
                current = self.model_options.get("top_p", "not set")
                self.chat_container.mount(
                    Static(f"[cyan]Current top-p: {current}[/]", classes="status")
                )
            else:
                try:
                    value = float(arg.strip())
                    if 0.0 <= value <= 1.0:
                        self.model_options["top_p"] = value
                        self.chat_container.mount(
                            Static(f"[green]Top-p set to {value}[/]", classes="status")
                        )
                    else:
                        self.chat_container.mount(
                            Static(
                                "[yellow]Top-p must be between 0.0 and 1.0[/]",
                                classes="status",
                            )
                        )
                except ValueError:
                    self.chat_container.mount(
                        Static(
                            "[yellow]Invalid top-p value. Use a number between 0.0 and 1.0[/]",
                            classes="status",
                        )
                    )
        elif cmd == "/export":
            # Save conversation to file
            if not arg:
                self.chat_container.mount(
                    Static("[yellow]Usage: /export <filepath>[/]", classes="status")
                )
            else:
                filepath = arg.strip()
                try:
                    # Export conversation messages
                    from pathlib import Path

                    output_path = Path(filepath)
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                    # Format conversation
                    lines = [f"# Conversation with {self.model_name}\n"]
                    for msg in self.messages:
                        role = msg["role"].upper()
                        content = msg.get("content", "")
                        lines.append(f"\n## {role}\n{content}\n")

                    output_path.write_text("\n".join(lines), encoding="utf-8")
                    self.chat_container.mount(
                        Static(
                            f"[green]✅ Conversation exported to: {filepath}[/]",
                            classes="status",
                        )
                    )
                except Exception as e:
                    self.chat_container.mount(
                        Static(
                            f"[red]Error exporting conversation: {e}[/]",
                            classes="status",
                        )
                    )
        elif cmd == "/prompt":
            tokens = [tok for tok in arg.split() if tok]
            if not tokens:
                self.chat_container.mount(
                    Static(
                        "[yellow]Usage: /prompt <name...> | remove <name> | clear[/]",
                        classes="status",
                    )
                )
            else:
                first = tokens[0].lower()
                if first in {"clear", "none"}:
                    self.active_prompt_templates = []
                    self.chat_container.mount(
                        Static("[green]Prompt templates cleared.[/]", classes="status")
                    )
                elif first == "remove":
                    if len(tokens) < 2:
                        self.chat_container.mount(
                            Static(
                                "[yellow]Usage: /prompt remove <name>[/]",
                                classes="status",
                            )
                        )
                    else:
                        name = tokens[1]
                        if name in self.active_prompt_templates:
                            self.active_prompt_templates = [
                                p for p in self.active_prompt_templates if p != name
                            ]
                            self.chat_container.mount(
                                Static(
                                    f"[green]Prompt '{name}' removed.[/]",
                                    classes="status",
                                )
                            )
                        else:
                            self.chat_container.mount(
                                Static(
                                    f"[yellow]Prompt '{name}' not active.[/]",
                                    classes="status",
                                )
                            )
                else:
                    activated = []
                    missing = []
                    for name in tokens:
                        content = await asyncio.to_thread(
                            prompts_manager.get_prompt, name
                        )
                        if not content:
                            missing.append(name)
                        else:
                            if name not in self.active_prompt_templates:
                                self.active_prompt_templates.append(name)
                            activated.append(name)
                    messages = []
                    if activated:
                        messages.append(
                            f"[green]Prompt(s) {', '.join(activated)} activated.[/]"
                        )
                    if missing:
                        messages.append(f"[yellow]Missing: {', '.join(missing)}[/]")
                    if not messages:
                        messages.append("[yellow]No prompts processed.[/]")
                    self.chat_container.mount(
                        Static("\n".join(messages), classes="status")
                    )
        elif cmd == "/prompts":
            tokens = [tok for tok in arg.split() if tok]
            if tokens and tokens[0].lower() == "active":
                if self.active_prompt_templates:
                    lines = ["[cyan]Active Prompts:[/cyan]"]
                    for name in self.active_prompt_templates:
                        lines.append(f"  [green]{name}[/green]")
                else:
                    lines = ["[cyan]Active Prompts:[/cyan]", "  (none)"]
                self.chat_container.mount(Static("\n".join(lines), classes="status"))
            else:
                page_arg = tokens[0] if tokens else ""
                page, warning = self.parse_page_argument(page_arg)
                if warning:
                    self.chat_container.mount(Static(warning, classes="status"))
                prompts = await asyncio.to_thread(prompts_manager.list_prompts)
                current_line = (
                    "[dim]Current: "
                    + (
                        ", ".join(self.active_prompt_templates)
                        if self.active_prompt_templates
                        else "(none)"
                    )
                    + "[/]"
                )
                self.show_template_list(
                    prompts,
                    page,
                    "Available Prompts:",
                    current_line=current_line,
                    store_state=True,
                )
        elif cmd == "/strategy":
            tokens = [tok for tok in arg.split() if tok]
            if not tokens:
                self.chat_container.mount(
                    Static(
                        "[yellow]Usage: /strategy <name> | clear[/]",
                        classes="status",
                    )
                )
            elif tokens[0].lower() in {"clear", "none"}:
                self.active_strategy_template = None
                self.chat_container.mount(
                    Static("[green]Strategy template cleared.[/]", classes="status")
                )
            else:
                target = tokens[0]
                content = await asyncio.to_thread(prompts_manager.get_strategy, target)
                if not content:
                    self.chat_container.mount(
                        Static(
                            f"[yellow]Strategy '{target}' not found.[/]",
                            classes="status",
                        )
                    )
                else:
                    self.active_strategy_template = target
                    self.chat_container.mount(
                        Static(
                            f"[green]Strategy '{target}' activated ({len(content)} chars).[/]",
                            classes="status",
                        )
                    )
        elif cmd == "/strategies":
            page_arg = arg.strip()
            page, warning = self.parse_page_argument(page_arg)
            if warning:
                self.chat_container.mount(Static(warning, classes="status"))
            strategies = await asyncio.to_thread(prompts_manager.list_strategies)
            current_line = (
                f"[dim]Current: {self.active_strategy_template}[/]"
                if self.active_strategy_template
                else "[dim]Current: (none)[/]"
            )
            self.show_template_list(
                strategies,
                page,
                "Available Strategies:",
                current_line=current_line,
                store_state=True,
            )
        elif cmd == "/model":
            if not arg:
                models = await asyncio.to_thread(models_config.get_models)
                active = await asyncio.to_thread(models_config.get_active_model)
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
                    self.chat_container.mount(
                        Static("\n".join(lines), classes="status")
                    )
            else:
                switched = await asyncio.to_thread(models_config.set_active_model, arg)
                if not switched:
                    self.chat_container.mount(
                        Static(f"[red]Model '{arg}' not found.[/]", classes="status")
                    )
                else:
                    new_model = await asyncio.to_thread(models_config.get_active_model)
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
                await asyncio.to_thread(models_config.refresh_ollama_models)
                self.chat_container.mount(
                    Static("[green]Model list reloaded.[/]", classes="status")
                )
            except Exception as exc:
                self.chat_container.mount(
                    Static(f"[red]Reload failed: {exc}[/]", classes="status")
                )
        elif cmd == "/consensus":
            # List or toggle consensus mode
            if not arg:
                # Show available consensus pipelines
                pipelines = consensus_config.list_pipelines()
                if pipelines:
                    pipeline_list = "\n".join(
                        [
                            (
                                f"  • [green]{p['name']}[/] ({p['type']}) - {p['description'][:50]}..."
                                if len(p["description"]) > 50
                                else f"  • [green]{p['name']}[/] ({p['type']}) - {p['description']}"
                            )
                            for p in pipelines
                        ]
                    )
                    self.chat_container.mount(
                        Static(
                            f"[cyan]Available Consensus Pipelines:[/]\n{pipeline_list}\n\n"
                            "[yellow]Usage: /consensus <pipeline_name>[/]",
                            classes="status",
                        )
                    )
                else:
                    self.chat_container.mount(
                        Static(
                            "[yellow]No consensus pipelines found.[/]\n"
                            "Create pipelines in ~/.orun/config.json or data/consensus/",
                            classes="status",
                        )
                    )
            else:
                # Set consensus mode (not implemented in TUI yet - show info)
                self.chat_container.mount(
                    Static(
                        f"[yellow]Consensus mode for TUI is not yet implemented.[/]\n"
                        f"Use single-shot mode instead:\n"
                        f'  orun "your prompt" --consensus {arg}',
                        classes="status",
                    )
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

            # Prepare messages with optional system prompt
            messages = self.messages.copy()
            if self.system_prompt and (
                not messages or messages[0].get("role") != "system"
            ):
                messages.insert(0, {"role": "system", "content": self.system_prompt})

            # Prepare model options
            options = self.model_options if self.model_options else None

            # Step 1: Initial Call (Sync)
            # If using tools, we assume we might get tool calls first (not streamed)
            # OR we can stream and parse? Ollama python lib `stream=True` yields chunks.
            # If `tools` is passed, Ollama usually returns one non-streamed response with tool_calls
            # OR a stream where one chunk contains them.
            # Safest is `stream=False` for the first hop if using tools.

            if self.use_tools:
                response = ollama.chat(
                    model=self.model_name,
                    messages=messages,
                    tools=tool_defs,
                    stream=False,
                    options=options,
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
                    self.stream_assistant_response(messages=messages, options=options)
                else:
                    # No tools, just content.
                    # But since we used stream=False, we have the full content already.
                    content = msg["content"]
                    self.app.call_from_thread(self.mount_message, "assistant", content)
                    db.add_message(self.conversation_id, "assistant", content)

            else:
                # No tools, just stream directly
                self.stream_assistant_response(messages=messages, options=options)

        except Exception as e:
            self.app.call_from_thread(
                self.chat_container.mount,
                Static(f"[red]Error: {e}[/]", classes="status"),
            )
        finally:
            self.app.call_from_thread(self.enable_input)

    def stream_assistant_response(self, messages=None, options=None):
        # Create the widget on the main thread
        widget = ChatMessage("assistant", "")
        self.app.call_from_thread(self.chat_container.mount, widget)
        self.app.call_from_thread(widget.scroll_visible)

        full_resp = ""
        # Use provided messages or default to self.messages
        msgs = messages if messages is not None else self.messages
        stream = ollama.chat(
            model=self.model_name, messages=msgs, stream=True, options=options
        )

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
