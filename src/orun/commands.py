from orun import core, db, prompts_manager
from orun.utils import Colors, print_error, print_success, print_info
from orun.rich_utils import console, create_table, print_table
from orun.tui import OrunApp


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
        table.add_row(alias, model_name, status, style=Colors.GREEN if model_name == active_model else None)

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
        first_msg = (
            messages[0]["content"][:50] + "..."
            if messages and len(messages[0]["content"]) > 50
            else (messages[0]["content"] if messages else "Empty")
        )
        table.add_row(str(conv["id"]), conv["model"], first_msg)

    print_table(table)
    console.print("\nUse 'orun c <id>' to continue a conversation.", style=Colors.YELLOW)


def cmd_continue(
    conversation_id: int,
    prompt: str = None,
    image_paths: list = None,
    model_override: str = None,
    use_tools: bool = False,
    yolo: bool = False,
):
    """Continue an existing conversation."""
    conv = db.get_conversation(conversation_id)
    if not conv:
        print_error(f"Conversation #{conversation_id} not found.")
        return

    model_name = model_override if model_override else conv["model"]

    # Set YOLO mode if requested (redundant if passed to run_chat_mode, but keeps local feedback)
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
        table = create_table("Available Strategy Templates", ["Strategy Name", "Description"])
        for strategy in strategies:
            description = prompts_manager.get_strategy(strategy)
            desc_preview = description[:50] + "..." if len(description) > 50 else description
            table.add_row(strategy, desc_preview, style=Colors.GREEN)
        print_table(table)
    else:
        console.print("No strategy templates found.", style=Colors.YELLOW)