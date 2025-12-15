from orun import core, db
from orun.utils import Colors, colored, print_error, print_success


def cmd_models():
    """Prints all available models and their aliases."""
    models = db.get_models()
    active_model = db.get_active_model()

    print(colored("\nAvailable Models:", Colors.YELLOW))
    if not models:
        print("  No models found.")
        return

    max_alias_len = max(len(alias) for alias in models.keys())

    for alias, model_name in models.items():
        marker = ""
        if model_name == active_model:
            marker = colored(" (active)", Colors.MAGENTA)

        print(
            f"  {colored(f'{alias:<{max_alias_len}}', Colors.GREEN)} : {colored(model_name, Colors.BLUE)}{marker}"
        )

    print(colored("\nUse -m <alias> to select a model.", Colors.YELLOW))


def cmd_history(limit: int = 10):
    """Prints recent conversations."""
    conversations = db.get_recent_conversations(limit)
    if not conversations:
        print(colored("No conversations found.", Colors.YELLOW))
        return

    print(colored("\nRecent Conversations:", Colors.YELLOW))
    # Reverse to show oldest first (within the recent limit), so newest is at the bottom
    for conv in reversed(conversations):
        messages = db.get_conversation_messages(conv["id"])
        first_msg = (
            messages[0]["content"][:50] + "..."
            if messages and len(messages[0]["content"]) > 50
            else (messages[0]["content"] if messages else "Empty")
        )
        print(
            f"  {colored(f'{conv["id"]:>3}', Colors.GREEN)} | {colored(f'{conv["model"]:<20}', Colors.BLUE)} | {first_msg}"
        )

    print(colored("\nUse 'orun c <id>' to continue a conversation.", Colors.YELLOW))


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
        # We can still print the message here or let run_chat_mode do it?
        # run_chat_mode doesn't print "YOLO MODE ENABLED" explicitly on start, only yolo.toggle does.
        # But wait, run_chat_mode prints special commands.
        print(colored("🔥 YOLO MODE ENABLED", Colors.RED))

    core.run_chat_mode(
        model_name,
        prompt or "",
        image_paths or [],
        conversation_id,
        use_tools=use_tools,
        yolo=yolo,
    )


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
    print(colored("🔄 Syncing models from Ollama...", Colors.CYAN))
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
