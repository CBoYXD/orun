from orun import core, db, prompts_manager, tools
from orun.rich_utils import console, create_table, print_table
from orun.search_config import search_config
from orun.consensus_config import consensus_config
from orun.tui import OrunApp
from orun.utils import Colors, print_error, print_success


def cmd_models():
    """Prints all available models and their aliases using a Rich table."""
    models = db.get_models()
    active_model = db.get_active_model()

    if not models:
        console.print("  No models found.", style=Colors.YELLOW)
        return

    table = create_table("Available Models", ["Alias", "Model", "Status"])

    for alias, model_name in models.items():
        status = "🟢 Active" if model_name == active_model else ""
        table.add_row(
            alias,
            model_name,
            status,
            style=Colors.GREEN if model_name == active_model else None,
        )

    print_table(table)
    console.print("\nUse -m <alias> to select a model.", style=Colors.YELLOW)


def cmd_history(limit: int = 10):
    """Prints recent conversations using a Rich table."""
    conversations = db.get_recent_conversations(limit)
    if not conversations:
        console.print("No conversations found.", style=Colors.YELLOW)
        return

    table = create_table("Recent Conversations", ["ID", "Model", "Preview"])

    # Reverse to show oldest first (within the recent limit), so newest is at the bottom
    for conv in reversed(conversations):
        messages = db.get_conversation_messages(conv["id"])
        preview_source = None
        if messages:
            for msg in messages:
                if not msg["role"].startswith("hidden_"):
                    preview_source = msg["content"]
                    break
            if preview_source is None:
                preview_source = "[hidden context]"
        else:
            preview_source = "Empty"

        first_msg = (
            preview_source[:50] + "..."
            if len(preview_source) > 50
            else preview_source
        )
        table.add_row(str(conv["id"]), conv["model"], first_msg)

    print_table(table)
    console.print(
        "\nUse 'orun c <id>' to continue a conversation.", style=Colors.YELLOW
    )


def cmd_continue(
    conversation_id: int,
    prompt: str = None,
    image_paths: list = None,
    model_override: str = None,
    use_tools: bool = False,
    yolo: bool = False,
    single_shot: bool = False,
):
    """Continue an existing conversation."""
    conv = db.get_conversation(conversation_id)
    if not conv:
        print_error(f"Conversation #{conversation_id} not found.")
        return

    model_name = model_override if model_override else conv["model"]

    if single_shot:
        # Run in single-shot mode
        core.run_continue_shot(
            conversation_id=conversation_id,
            user_prompt=prompt or "",
            image_paths=image_paths or [],
            model_name=model_name,
            use_tools=use_tools,
            yolo=yolo,
        )
    else:
        # Run in interactive mode
        if yolo:
            console.print("🔥 YOLO MODE ENABLED", style=Colors.RED)

        app = OrunApp(
            model_name=model_name,
            initial_prompt=prompt or "",
            initial_images=image_paths or [],
            conversation_id=conversation_id,
            use_tools=use_tools,
            yolo=yolo,
        )
        app.run()


def cmd_last(
    prompt: str = None,
    image_paths: list = None,
    model_override: str = None,
    use_tools: bool = False,
    yolo: bool = False,
    single_shot: bool = False,
):
    """Continue the last conversation."""
    conversation_id = db.get_last_conversation_id()
    if not conversation_id:
        print_error("No conversations found.")
        return

    cmd_continue(
        conversation_id,
        prompt,
        image_paths,
        model_override,
        use_tools=use_tools,
        yolo=yolo,
        single_shot=single_shot,
    )


def cmd_refresh():
    """Syncs models from Ollama."""
    console.print("🔄 Syncing models from Ollama...", style=Colors.CYAN)
    db.refresh_ollama_models()


def cmd_shortcut(identifier: str, new_shortcut: str):
    """Updates a model's shortcut."""
    if db.update_model_shortcut(identifier, new_shortcut):
        print_success(
            f"Shortcut updated: {new_shortcut} -> {identifier} (or resolved full name)"
        )
    else:
        print_error(
            f"Could not update shortcut. Model '{identifier}' not found or shortcut '{new_shortcut}' already taken."
        )


def cmd_set_active(target: str):
    """Sets the active model."""
    db.set_active_model(target)
    active = db.get_active_model()
    if active:
        print_success(f"Active model set to: {active}")
    else:
        print_error(f"Could not set active model. '{target}' not found.")


def cmd_prompts():
    """Lists all available prompt templates using a Rich table."""
    prompts = prompts_manager.list_prompts()
    if prompts:
        table = create_table("Available Prompt Templates", ["Template Name"])
        for prompt in prompts:
            table.add_row(prompt, style=Colors.GREEN)
        print_table(table)
    else:
        console.print("No prompt templates found.", style=Colors.YELLOW)


def cmd_strategies():
    """Lists all available strategy templates using a Rich table."""
    strategies = prompts_manager.list_strategies()
    if strategies:
        table = create_table(
            "Available Strategy Templates", ["Strategy Name", "Description"]
        )
        for strategy in strategies:
            description = prompts_manager.get_strategy(strategy)
            desc_preview = (
                description[:50] + "..." if len(description) > 50 else description
            )
            table.add_row(strategy, desc_preview, style=Colors.GREEN)
        print_table(table)
    else:
        console.print("No strategy templates found.", style=Colors.YELLOW)


def cmd_config_search(api_key: str = None, cse_id: str = None):
    """Configure Google Custom Search API credentials."""
    if not api_key or not cse_id:
        # Show current configuration
        console.print("\n[cyan]Google Search Configuration:[/cyan]")

        if search_config.has_google_credentials():
            console.print("  ✅ Google API configured", style=Colors.GREEN)
            console.print(f"  API Key: {search_config.google_api_key[:10]}...{search_config.google_api_key[-4:]}", style=Colors.DIM)
            console.print(f"  CSE ID: {search_config.google_cse_id}", style=Colors.DIM)
        else:
            console.print("  ❌ Google API not configured (using DuckDuckGo fallback)", style=Colors.YELLOW)

        console.print(f"\n  Config file: {search_config.config_path}", style=Colors.DIM)
        console.print("\n[yellow]Usage:[/yellow]")
        console.print("  orun config-search <api_key> <cse_id>", style=Colors.CYAN)
        console.print("\n[yellow]Get credentials:[/yellow]")
        console.print("  API Key: https://console.cloud.google.com/", style=Colors.DIM)
        console.print("  CSE ID: https://programmablesearchengine.google.com/", style=Colors.DIM)
        return

    # Save credentials
    if search_config.save_google_credentials(api_key, cse_id):
        print_success("✅ Google Search API configured successfully!")
        console.print(f"  Config saved to: {search_config.config_path}", style=Colors.DIM)
        console.print("\n  Web search will now use Google API (100 free queries/day)", style=Colors.GREEN)
        console.print("  Fallback to DuckDuckGo when quota exceeded", style=Colors.DIM)
    else:
        print_error("Failed to save Google Search API credentials.")


def cmd_arxiv(query: str):
    """Search or fetch arXiv papers."""
    # Detect if it's an arXiv ID or a search query
    # arXiv IDs are typically in format: YYMM.NNNNN or archive/YYYYNNNNN
    query = query.strip()

    # Check if it looks like an arXiv ID
    is_arxiv_id = False
    if "/" in query or "." in query:
        # Could be an ID like "2301.07041" or "cs/0001001"
        # or a URL like "https://arxiv.org/abs/2301.07041"
        if "arxiv.org" in query or query.replace(".", "").replace("/", "").replace("v", "").isdigit():
            is_arxiv_id = True

    console.print(f"🔍 {'Fetching arXiv paper' if is_arxiv_id else 'Searching arXiv'}...", style=Colors.CYAN)

    if is_arxiv_id:
        result = tools.get_arxiv_paper(query)
    else:
        result = tools.search_arxiv(query)

    console.print("\n" + result, style=Colors.GREY)


def cmd_search(query: str):
    """Search the web."""
    console.print(f"🔍 Searching the web for: {query}", style=Colors.CYAN)
    result = tools.web_search(query)
    console.print("\n" + result, style=Colors.GREY)


def cmd_fetch(url: str):
    """Fetch and display content from a URL."""
    console.print(f"🌐 Fetching: {url}", style=Colors.CYAN)
    result = tools.fetch_url(url)
    console.print("\n" + result, style=Colors.GREY)


def cmd_consensus_list():
    """Lists all available consensus pipelines using a Rich table."""
    pipelines = consensus_config.list_pipelines()
    if pipelines:
        table = create_table(
            "Available Consensus Pipelines",
            ["Name", "Type", "Models", "Description"]
        )
        for pipeline in pipelines:
            table.add_row(
                pipeline["name"],
                pipeline["type"],
                str(pipeline["models_count"]),
                pipeline["description"][:60] + "..." if len(pipeline["description"]) > 60 else pipeline["description"],
                style=Colors.GREEN
            )
        print_table(table)
        console.print(
            "\nUse: orun \"your prompt\" --consensus <name>",
            style=Colors.YELLOW
        )
        console.print(
            "Or in chat: /consensus <name>",
            style=Colors.YELLOW
        )
    else:
        console.print("No consensus pipelines found.", style=Colors.YELLOW)
        console.print(
            "Create pipelines in ~/.orun/config.json or data/consensus/",
            style=Colors.GREY
        )


def cmd_consensus_config():
    """Show consensus configuration path and info."""
    import platform
    import subprocess

    config_path = consensus_config.config_path

    console.print("\n[cyan]Consensus Configuration:[/cyan]")
    console.print(f"  Config file: {config_path}", style=Colors.GREY)

    if config_path.exists():
        console.print(f"  Status: [green]Found[/green]")

        # Count user-defined pipelines
        import json
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                user_pipelines = config.get("consensus", {}).get("pipelines", {})
                console.print(
                    f"  User pipelines: {len(user_pipelines)}",
                    style=Colors.GREY
                )
        except Exception:
            pass
    else:
        console.print(f"  Status: [yellow]Not found (will be created on first use)[/yellow]")

    # Show default pipelines location
    console.print(f"  Default pipelines: {consensus_config.data_dir}", style=Colors.GREY)
    if consensus_config.data_dir.exists():
        default_count = len(list(consensus_config.data_dir.glob("*.json")))
        console.print(
            f"  Default count: {default_count}",
            style=Colors.GREY
        )

    console.print()

    # Open in editor if exists
    if config_path.exists():
        should_open = console.input(
            "[yellow]Open config file in default editor? [y/N]: [/yellow]"
        ).lower()

        if should_open == "y":
            try:
                if platform.system() == "Windows":
                    subprocess.run(["notepad", str(config_path)])
                elif platform.system() == "Darwin":
                    subprocess.run(["open", str(config_path)])
                else:
                    subprocess.run(["xdg-open", str(config_path)])
            except Exception as e:
                print_error(f"Could not open editor: {e}")
    else:
        console.print(
            "Run any consensus command to create the config file.",
            style=Colors.YELLOW
        )
