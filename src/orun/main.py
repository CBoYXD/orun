import argparse
import os
import sys

from orun import commands, consensus, core, db, profiles_manager, utils
from orun.models_config import models_config
from orun.rich_utils import Colors, console, print_warning
from orun.tui import OrunApp

SUBCOMMANDS = {
    "models",
    "refresh",
    "shortcut",
    "set-active",
    "history",
    "prompts",
    "strategies",
    "profiles",
    "arxiv",
    "search",
    "fetch",
    "consensus",
    "consensus-config",
    "export",
    "import",
    "chat",
    "c",
    "last",
    "mcp-server",
}

EPILOG = """
Examples:
  # File context
  orun "review code" -f src/main.py -f src/core.py
  orun "analyze" --dir src/

  # Pipe support
  git diff | orun "review changes"
  cat error.log | orun "explain this error"

  # Quick lookups
  orun arxiv "transformer attention"
  orun search "python best practices"
  orun fetch https://example.com

  # Consensus pipelines
  orun consensus
  orun "Write a REST API" -C code_review
  orun "Analyze microservices" -C multi_expert

  # Output options
  orun "generate client" -o client.py
  orun "improve text" --from-clipboard --to-clipboard

  # Continue conversations
  orun c 42 "add tests" --single-shot
  orun last "add error handling" --single-shot

  # Advanced
  orun "task" -p review_code -p security -s cot
  orun "story" --temperature 0.9 --system "Be creative"
  result=$(orun "query" -q)
"""


@utils.handle_cli_errors
def main():
    utils.setup_console()
    utils.ensure_orun_config()

    # Ensure Ollama is running and FunctionGemma is available (Mandatory)
    utils.ensure_ollama_running()
    if not utils.ensure_function_gemma_available(auto_download=True):
        console.print("\n[red]CRITICAL: FunctionGemma model is required.[/red]")
        console.print("[red]The application cannot function without this model.[/red]")
        sys.exit(1)

    db.initialize()

    models = models_config.get_models()

    if len(sys.argv) > 1 and sys.argv[1] in SUBCOMMANDS:
        parser = build_command_parser()
        args = parser.parse_args()
        dispatch_command(args, models)
        return

    parser = build_single_shot_parser()
    args = parser.parse_args()
    dispatch_single_shot(args, models, parser)


def build_single_shot_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI CLI wrapper for Ollama with powerful single-shot capabilities",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("prompt", nargs="*", help="Text prompt")
    parser.add_argument("-m", "--model", default="default", help="Model alias or name")
    parser.add_argument("-i", "--images", nargs="*", type=str, help="Screenshot indices")
    parser.add_argument(
        "-f",
        "--files",
        nargs="*",
        type=str,
        help="Files to include as context (supports glob patterns)",
    )
    parser.add_argument("--dir", type=str, help="Directory to scan and include as context (recursive)")
    parser.add_argument(
        "-p",
        "--prompt",
        dest="use_prompt",
        action="append",
        help="Use prompt template(s) (can be used multiple times)",
    )
    parser.add_argument(
        "-s",
        "--strategy",
        dest="use_strategy",
        action="append",
        help="Use strategy template(s) (can be used multiple times)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Save output to file instead of printing to console",
    )
    parser.add_argument("--system", type=str, help="Custom system prompt to guide the AI's behavior")
    parser.add_argument(
        "--from-clipboard", action="store_true", help="Read input from clipboard"
    )
    parser.add_argument("--to-clipboard", action="store_true", help="Copy output to clipboard")
    parser.add_argument(
        "--temperature",
        type=float,
        help="Model temperature (0.0-2.0, default: varies by model)",
    )
    parser.add_argument(
        "--top-p", type=float, help="Top-p sampling (0.0-1.0, default: varies by model)"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet mode: suppress progress messages")
    parser.add_argument("--yolo", action="store_true", help="Enable YOLO mode (no confirmations)")
    parser.add_argument(
        "-C",
        "--consensus",
        type=str,
        metavar="PIPELINE",
        help="Use consensus pipeline instead of single model",
    )
    parser.add_argument("--profile", dest="profile", help="Use a specific profile (included prompts)")
    return parser


def build_command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orun",
        description="AI CLI wrapper for Ollama commands",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("models", help="List available models")
    subparsers.add_parser("refresh", help="Sync models from Ollama")

    shortcut = subparsers.add_parser("shortcut", help="Add a shortcut to a model")
    shortcut.add_argument("identifier", help="Model name or shortcut")
    shortcut.add_argument("new_shortcut", help="New shortcut")

    set_active = subparsers.add_parser("set-active", help="Set active model")
    set_active.add_argument("target", help="Model name or shortcut")

    history = subparsers.add_parser("history", help="List recent conversations")
    history.add_argument("-n", type=int, default=10, help="Number of conversations to show")

    prompts = subparsers.add_parser("prompts", help="List available prompt templates")
    prompts.add_argument("--show", dest="show", help="Show a specific prompt template")

    strategies = subparsers.add_parser("strategies", help="List available strategy templates")
    strategies.add_argument("--show", dest="show", help="Show a specific strategy template")

    subparsers.add_parser("profiles", help="List available profiles")

    arxiv = subparsers.add_parser("arxiv", help="Search or fetch arXiv papers")
    arxiv.add_argument("query", nargs="+", help="Search query or arXiv ID")

    search = subparsers.add_parser("search", help="Search the web (DuckDuckGo)")
    search.add_argument("query", nargs="+", help="Search query")

    fetch = subparsers.add_parser("fetch", help="Fetch and display web content")
    fetch.add_argument("url", help="URL to fetch")

    mcp_server = subparsers.add_parser("mcp-server", help="Start optional Robyn MCP server")
    mcp_server.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    mcp_server.add_argument(
        "--port", type=int, default=8000, help="Port to bind the MCP server (default: 8000)"
    )
    mcp_server.add_argument(
        "-m",
        "--model",
        help="Model alias or name to serve. Defaults to the active model if not provided.",
    )
    mcp_server.add_argument(
        "--disable-tools",
        action="store_true",
        help="Disable tool usage for requests handled by the MCP server.",
    )

    subparsers.add_parser("consensus", help="List available consensus pipelines")
    subparsers.add_parser("consensus-config", help="Configure consensus pipelines")

    export = subparsers.add_parser("export", help="Export a conversation")
    export.add_argument("id", type=int, help="Conversation ID to export")
    export.add_argument("-o", "--output", help="Output file path")
    export.add_argument(
        "-f",
        "--format",
        choices=["json", "md", "markdown"],
        default="json",
        help="Export format (default: json)",
    )

    import_cmd = subparsers.add_parser("import", help="Import a conversation")
    import_cmd.add_argument("file", help="JSON export file")

    chat = subparsers.add_parser("chat", help="Start interactive chat session")
    chat.add_argument("prompt", nargs="*", help="Initial prompt")
    chat.add_argument("-m", "--model", help="Override model")
    chat.add_argument("-i", "--images", nargs="*", type=str, help="Screenshot indices")
    chat.add_argument("-p", "--prompt", dest="use_prompt", help="Use a specific prompt template")
    chat.add_argument("-s", "--strategy", dest="use_strategy", help="Use a specific strategy template")
    chat.add_argument("--yolo", action="store_true", help="Enable YOLO mode (no confirmations)")
    chat.add_argument("--profile", dest="profile", help="Use a specific profile (system prompt)")

    cont = subparsers.add_parser("c", help="Continue a conversation by ID")
    cont.add_argument("id", type=int, help="Conversation ID")
    cont.add_argument("prompt", nargs="*", help="Initial prompt")
    cont.add_argument("-m", "--model", help="Override model")
    cont.add_argument("-i", "--images", nargs="*", type=str, help="Screenshot indices")
    cont.add_argument("--single-shot", action="store_true", help="Run in single-shot mode")
    cont.add_argument("--yolo", action="store_true", help="Enable YOLO mode (no confirmations)")

    last = subparsers.add_parser("last", help="Continue last conversation")
    last.add_argument("prompt", nargs="*", help="Initial prompt")
    last.add_argument("-m", "--model", help="Override model")
    last.add_argument("-i", "--images", nargs="*", type=str, help="Screenshot indices")
    last.add_argument("--single-shot", action="store_true", help="Run in single-shot mode")
    last.add_argument("--yolo", action="store_true", help="Enable YOLO mode (no confirmations)")

    return parser


def dispatch_command(args: argparse.Namespace, models: dict) -> None:
    if args.command == "models":
        commands.cmd_models()
        return
    if args.command == "refresh":
        commands.cmd_refresh()
        return
    if args.command == "shortcut":
        commands.cmd_shortcut(args.identifier, args.new_shortcut)
        return
    if args.command == "set-active":
        commands.cmd_set_active(args.target)
        return
    if args.command == "history":
        commands.cmd_history(args.n)
        return
    if args.command == "prompts":
        commands.cmd_prompts(args.show)
        return
    if args.command == "strategies":
        commands.cmd_strategies(args.show)
        return
    if args.command == "profiles":
        commands.cmd_profiles()
        return
    if args.command == "arxiv":
        commands.cmd_arxiv(" ".join(args.query))
        return
    if args.command == "search":
        commands.cmd_search(" ".join(args.query))
        return
    if args.command == "fetch":
        commands.cmd_fetch(args.url)
        return
    if args.command == "mcp-server":
        commands.cmd_mcp_server(args.host, args.port, args.model, args.disable_tools)
        return
    if args.command == "consensus":
        commands.cmd_consensus_list()
        return
    if args.command == "consensus-config":
        commands.cmd_consensus_config()
        return
    if args.command == "export":
        commands.cmd_export(args.id, args.output, args.format)
        return
    if args.command == "import":
        commands.cmd_import(args.file)
        return
    if args.command == "chat":
        dispatch_chat(args, models)
        return
    if args.command == "c":
        dispatch_continue(args, models)
        return
    if args.command == "last":
        dispatch_last(args, models)
        return


def dispatch_chat(args: argparse.Namespace, models: dict) -> None:
    image_paths = utils.get_image_paths(args.images)

    system_profile = profiles_manager.get_profile("system")
    profile_prompts = system_profile.included_prompts if system_profile else []
    profile_strategy = None

    if args.profile:
        profile = profiles_manager.get_profile(args.profile)
        if profile:
            if profile.included_prompts:
                profile_prompts = profile_prompts + profile.included_prompts
            profile_strategy = profile.strategy
            console.print(
                f"Using profile: {args.profile} ({len(profile.included_prompts)} prompts)",
                style=Colors.CYAN,
            )
        else:
            print_warning(
                f"Profile '{args.profile}' not found. Run 'orun profiles' to see available profiles."
            )

    model_name = (
        models.get(args.model, args.model)
        if args.model
        else models_config.get_active_model()
    )

    if not model_name:
        console.print("No active model set.", style=Colors.RED)
        console.print(
            "Please specify a model with -m <model> or set a default with orun set-active <model>",
            style=Colors.YELLOW,
        )
        return

    if args.model:
        models_config.set_active_model(model_name)

    initial_prompts = profile_prompts or []
    if args.use_prompt:
        initial_prompts.append(args.use_prompt)

    initial_strategy = args.use_strategy or profile_strategy

    app = OrunApp(
        model_name=model_name,
        initial_prompt=" ".join(args.prompt) if args.prompt else None,
        initial_images=image_paths,
        use_tools=True,
        yolo=args.yolo,
        initial_prompt_templates=initial_prompts if initial_prompts else None,
        initial_strategy_template=initial_strategy,
    )

    app.run()


def dispatch_continue(args: argparse.Namespace, models: dict) -> None:
    image_paths = utils.get_image_paths(args.images)
    model_override = models.get(args.model, args.model) if args.model else None
    if not model_override:
        conv = db.get_conversation(args.id)
        if conv:
            model_override = conv["model"]

    if model_override:
        models_config.set_active_model(model_override)

    commands.cmd_continue(
        args.id,
        " ".join(args.prompt) if args.prompt else None,
        image_paths,
        model_override,
        use_tools=True,
        yolo=args.yolo,
        single_shot=args.single_shot,
    )


def dispatch_last(args: argparse.Namespace, models: dict) -> None:
    image_paths = utils.get_image_paths(args.images)

    model_override = models.get(args.model, args.model) if args.model else None
    if not model_override:
        cid = db.get_last_conversation_id()
        if cid:
            conv = db.get_conversation(cid)
            if conv:
                model_override = conv["model"]

    if model_override:
        models_config.set_active_model(model_override)

    commands.cmd_last(
        " ".join(args.prompt) if args.prompt else None,
        image_paths,
        model_override,
        use_tools=True,
        yolo=args.yolo,
        single_shot=args.single_shot,
    )


def dispatch_single_shot(
    args: argparse.Namespace, models: dict, parser: argparse.ArgumentParser
) -> None:
    model_name = None
    if args.model != "default":
        model_name = models.get(args.model, args.model)
        models_config.set_active_model(model_name)
    else:
        model_name = models_config.get_active_model()

    if not model_name:
        console.print("No active model set.", style=Colors.RED)
        console.print(
            "Please specify a model with -m <model> or set a default with orun set-active <model>",
            style=Colors.YELLOW,
        )
        return

    user_prompt = " ".join(args.prompt) if args.prompt else ""
    image_paths = utils.get_image_paths(args.images)

    file_paths = []
    if args.files:
        file_paths = utils.parse_file_patterns(args.files)

    dir_context = None
    if args.dir:
        dir_context = utils.read_directory_context(args.dir, exclude_paths=file_paths)

    stdin_content = utils.read_stdin()

    clipboard_content = None
    if args.from_clipboard:
        clipboard_content = utils.read_clipboard_text()

    if (
        not user_prompt
        and not image_paths
        and not file_paths
        and not dir_context
        and not stdin_content
        and not clipboard_content
        and not args.use_prompt
        and not args.use_strategy
        and not args.profile
    ):
        parser.print_help()
        return

    model_options = {}
    if args.temperature is not None:
        model_options["temperature"] = args.temperature
    if args.top_p is not None:
        model_options["top_p"] = args.top_p

    if args.consensus:
        if args.use_prompt or args.use_strategy:
            print_warning(
                "Warning: Prompt/strategy templates are not applied in consensus modes."
            )
            print_warning("Use system prompts in the pipeline configuration instead.")

        output = consensus.run_consensus(
            pipeline_name=args.consensus,
            user_prompt=user_prompt,
            image_paths=image_paths,
            system_prompt=args.system,
            tools_enabled=True,
            yolo_mode=args.yolo,
            model_options=model_options if model_options else None,
        )

        if args.output:
            utils.write_to_file(args.output, output)
        if args.to_clipboard:
            utils.copy_to_clipboard(output)
        return

    system_profile = profiles_manager.get_profile("system")
    profile_prompts = system_profile.included_prompts if system_profile else []
    profile_strategy = None

    if args.profile:
        profile = profiles_manager.get_profile(args.profile)
        if profile:
            if profile.included_prompts:
                profile_prompts = profile_prompts + profile.included_prompts
            profile_strategy = profile.strategy
            if not args.quiet:
                console.print(
                    f"Using profile: {args.profile} ({len(profile.included_prompts)} prompts)",
                    style=Colors.CYAN,
                )
        else:
            print_warning(
                f"Profile '{args.profile}' not found. Run 'orun profiles' to see available profiles."
            )

    merged_prompts = profile_prompts + (args.use_prompt or [])
    merged_strategy = args.use_strategy or (
        [profile_strategy] if profile_strategy else None
    )

    core.run_single_shot(
        model_name,
        user_prompt,
        image_paths,
        use_tools=True,
        yolo=args.yolo,
        prompt_template=merged_prompts if merged_prompts else None,
        strategy_template=merged_strategy if merged_strategy else None,
        file_paths=file_paths,
        stdin_content=stdin_content,
        output_file=args.output,
        system_prompt=args.system,
        dir_context=dir_context,
        clipboard_content=clipboard_content,
        to_clipboard=args.to_clipboard,
        model_options=model_options if model_options else None,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n👋 Goodbye!", style=Colors.GREY)
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
