import argparse
import os
import sys

from orun import commands, core, db, utils
from orun.rich_utils import console
from orun.tui import OrunApp
from orun.utils import Colors, print_warning


@utils.handle_cli_errors
def main():
    # Setup

    utils.setup_console()

    db.initialize()

    models = db.get_models()

    # Subcommand Dispatch

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "models":
            commands.cmd_models()

            return

        if cmd == "refresh":
            commands.cmd_refresh()

            return

        if cmd == "shortcut":
            if len(sys.argv) < 4:
                print_warning(
                    "Usage: orun shortcut <model_name_or_shortcut> <new_shortcut>"
                )

                return

            commands.cmd_shortcut(sys.argv[2], sys.argv[3])

            return

        if cmd == "set-active":
            if len(sys.argv) < 3:
                print_warning("Usage: orun set-active <model_name_or_shortcut>")

                return

            commands.cmd_set_active(sys.argv[2])

            return

        if cmd == "history":
            parser = argparse.ArgumentParser(prog="orun history")

            parser.add_argument(
                "-n", type=int, default=10, help="Number of conversations to show"
            )

            args = parser.parse_args(sys.argv[2:])

            commands.cmd_history(args.n)

            return

        if cmd == "prompts":
            commands.cmd_prompts()

            return

        if cmd == "strategies":
            commands.cmd_strategies()

            return

        if cmd == "config-search":
            if len(sys.argv) == 2:
                # Show current config
                commands.cmd_config_search()
            elif len(sys.argv) == 4:
                # Set config with api_key and cse_id
                commands.cmd_config_search(sys.argv[2], sys.argv[3])
            else:
                print_warning("Usage: orun config-search <api_key> <cse_id>")
                print_warning("   or: orun config-search  (to view current config)")

            return

        if cmd == "arxiv":
            if len(sys.argv) < 3:
                print_warning("Usage: orun arxiv <query or arxiv_id>")
                return

            commands.cmd_arxiv(" ".join(sys.argv[2:]))
            return

        if cmd == "search":
            if len(sys.argv) < 3:
                print_warning("Usage: orun search <query>")
                return

            commands.cmd_search(" ".join(sys.argv[2:]))
            return

        if cmd == "fetch":
            if len(sys.argv) < 3:
                print_warning("Usage: orun fetch <url>")
                return

            commands.cmd_fetch(sys.argv[2])
            return

        if cmd == "chat":
            parser = argparse.ArgumentParser(prog="orun chat")

            parser.add_argument("prompt", nargs="*", help="Initial prompt")

            parser.add_argument("-m", "--model", help="Override model")

            parser.add_argument(
                "-i", "--images", nargs="*", type=str, help="Screenshot indices"
            )

            parser.add_argument(
                "-p",
                "--prompt",
                dest="use_prompt",
                help="Use a specific prompt template",
            )

            parser.add_argument(
                "-s",
                "--strategy",
                dest="use_strategy",
                help="Use a specific strategy template",
            )

            parser.add_argument(
                "--yolo",
                action="store_true",
                help="Enable YOLO mode (no confirmations)",
            )

            args = parser.parse_args(sys.argv[2:])

            image_paths = utils.get_image_paths(args.images)

            # Resolve model

            model_name = (
                models.get(args.model, args.model)
                if args.model
                else db.get_active_model()
            )

            if not model_name:
                console.print("No active model set.", style=Colors.RED)

                console.print(
                    "Please specify a model with -m <model> or set a default with orun set-active <model>",
                    style=Colors.YELLOW,
                )

                return

            if args.model:
                db.set_active_model(model_name)

            app = OrunApp(
                model_name=model_name,
                initial_prompt=" ".join(args.prompt) if args.prompt else None,
                initial_images=image_paths,
                use_tools=True,
                yolo=args.yolo,
                initial_prompt_template=args.use_prompt,
                initial_strategy_template=args.use_strategy,
            )

            app.run()

            return

        if cmd == "c":
            parser = argparse.ArgumentParser(prog="orun c")
            parser.add_argument("id", type=int, help="Conversation ID")
            parser.add_argument("prompt", nargs="*", help="Initial prompt")
            parser.add_argument("-m", "--model", help="Override model")
            parser.add_argument(
                "-i", "--images", nargs="*", type=str, help="Screenshot indices"
            )
            parser.add_argument(
                "--single-shot",
                action="store_true",
                help="Run in single-shot mode (exit after response)",
            )
            parser.add_argument(
                "--yolo",
                action="store_true",
                help="Enable YOLO mode (no confirmations)",
            )
            args = parser.parse_args(sys.argv[2:])

            image_paths = utils.get_image_paths(args.images)

            # Resolve model override
            model_override = models.get(args.model, args.model) if args.model else None
            if not model_override:
                conv = db.get_conversation(args.id)
                if conv:
                    model_override = conv["model"]

            if model_override:
                db.set_active_model(model_override)

            # Always enable tools
            commands.cmd_continue(
                args.id,
                " ".join(args.prompt) if args.prompt else None,
                image_paths,
                model_override,
                use_tools=True,
                yolo=args.yolo,
                single_shot=args.single_shot,
            )
            return

        if cmd == "last":
            parser = argparse.ArgumentParser(prog="orun last")
            parser.add_argument("prompt", nargs="*", help="Initial prompt")
            parser.add_argument("-m", "--model", help="Override model")
            parser.add_argument(
                "-i", "--images", nargs="*", type=str, help="Screenshot indices"
            )
            parser.add_argument(
                "--single-shot",
                action="store_true",
                help="Run in single-shot mode (exit after response)",
            )
            parser.add_argument(
                "--yolo",
                action="store_true",
                help="Enable YOLO mode (no confirmations)",
            )
            args = parser.parse_args(sys.argv[2:])

            image_paths = utils.get_image_paths(args.images)

            # Resolve model override
            model_override = models.get(args.model, args.model) if args.model else None
            if not model_override:
                cid = db.get_last_conversation_id()
                if cid:
                    conv = db.get_conversation(cid)
                    if conv:
                        model_override = conv["model"]

            if model_override:
                db.set_active_model(model_override)

            # Always enable tools
            commands.cmd_last(
                " ".join(args.prompt) if args.prompt else None,
                image_paths,
                model_override,
                use_tools=True,
                yolo=args.yolo,
                single_shot=args.single_shot,
            )
            return

    # Default Query Mode (Single Shot)
    parser = argparse.ArgumentParser(
        description="AI CLI wrapper for Ollama",
        usage="orun [command] [prompt] [options]\n\nCommands:\n  chat            Start interactive chat session\n  arxiv <query>   Search or fetch arXiv papers\n  search <query>  Search the web\n  fetch <url>     Fetch and display web content\n  models          List available models\n  refresh         Sync models from Ollama\n  shortcut        Change model shortcut\n  set-active      Set active model\n  history         List recent conversations\n  prompts         List available prompt templates\n  strategies      List available strategy templates\n  config-search   Configure Google Search API credentials\n  c <id>          Continue conversation by ID\n  last            Continue last conversation\n\nSingle-shot options:\n  -p <prompt>     Use a specific prompt template\n  -s <strategy>   Use a specific strategy template\n  -f <file>       Add file(s) as context (supports globs)",
    )
    parser.add_argument("prompt", nargs="*", help="Text prompt")
    parser.add_argument("-m", "--model", default="default", help="Model alias or name")
    parser.add_argument(
        "-i", "--images", nargs="*", type=str, help="Screenshot indices"
    )
    parser.add_argument(
        "-f", "--files", nargs="*", type=str, help="Files to include as context (supports glob patterns)"
    )
    parser.add_argument(
        "-p", "--prompt", dest="use_prompt", help="Use a specific prompt template"
    )
    parser.add_argument(
        "-s", "--strategy", dest="use_strategy", help="Use a specific strategy template"
    )
    parser.add_argument(
        "-o", "--output", type=str, help="Save output to file instead of printing to console"
    )
    parser.add_argument(
        "--system", type=str, help="Custom system prompt to guide the AI's behavior"
    )
    parser.add_argument(
        "--yolo", action="store_true", help="Enable YOLO mode (no confirmations)"
    )

    args = parser.parse_args()

    # Resolve Model
    model_name = None
    if args.model != "default":
        # User explicitly asked for a model
        model_name = models.get(args.model, args.model)
        # Update active model
        db.set_active_model(model_name)
    else:
        # User didn't specify, use active
        model_name = db.get_active_model()

    if not model_name:
        console.print("No active model set.", style=Colors.RED)
        console.print(
            "Please specify a model with -m <model> or set a default with orun set-active <model>",
            style=Colors.YELLOW,
        )
        return

    user_prompt = " ".join(args.prompt) if args.prompt else ""
    image_paths = utils.get_image_paths(args.images)

    # Process file arguments
    file_paths = []
    if args.files:
        file_paths = utils.parse_file_patterns(args.files)

    # Check for stdin input (pipe support)
    stdin_content = utils.read_stdin()

    # If no prompt/images/files/stdin provided, but have a prompt/strategy template, show help
    if (
        not user_prompt
        and not image_paths
        and not file_paths
        and not stdin_content
        and not args.use_prompt
        and not args.use_strategy
    ):
        parser.print_help()
        return

    # Always enable tools for single shot too
    core.run_single_shot(
        model_name,
        user_prompt,
        image_paths,
        use_tools=True,
        yolo=args.yolo,
        prompt_template=args.use_prompt,
        strategy_template=args.use_strategy,
        file_paths=file_paths,
        stdin_content=stdin_content,
        output_file=args.output,
        system_prompt=args.system,
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
