import argparse
import os
import sys

from orun import commands, consensus, core, db, profiles_manager, utils
from orun.models_config import models_config
from orun.rich_utils import Colors, console, print_warning
from orun.tui import OrunApp


@utils.handle_cli_errors
def main():
    # Setup

    utils.setup_console()

    # Ensure Ollama is running and FunctionGemma is available (Mandatory)
    utils.ensure_ollama_running()
    if not utils.ensure_function_gemma_available(auto_download=True):
        console.print("\n[red]CRITICAL: FunctionGemma model is required.[/red]")
        console.print("[red]The application cannot function without this model.[/red]")
        sys.exit(1)

    db.initialize()

    models = models_config.get_models()

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

        if cmd == "profiles":
            commands.cmd_profiles()

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

        if cmd == "consensus":
            commands.cmd_consensus_list()
            return

        if cmd == "consensus-config":
            commands.cmd_consensus_config()
            return

        if cmd == "export":
            parser = argparse.ArgumentParser(prog="orun export")
            parser.add_argument("id", type=int, help="Conversation ID to export")
            parser.add_argument("-o", "--output", help="Output file path")
            parser.add_argument(
                "-f",
                "--format",
                choices=["json", "md", "markdown"],
                default="json",
                help="Export format (default: json)",
            )
            args = parser.parse_args(sys.argv[2:])
            commands.cmd_export(args.id, args.output, args.format)
            return

        if cmd == "import":
            if len(sys.argv) < 3:
                print_warning("Usage: orun import <file.json>")
                return
            commands.cmd_import(sys.argv[2])
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

            parser.add_argument(
                "--profile",
                dest="profile",
                help="Use a specific profile (system prompt)",
            )

            args = parser.parse_args(sys.argv[2:])

            image_paths = utils.get_image_paths(args.images)

            # Load profile if specified
            # Always load system profile (can be overridden by user)
            system_profile = profiles_manager.get_profile("system")
            profile_prompts = system_profile.included_prompts if system_profile else []
            profile_strategy = None

            # Load user-specified profile and merge with system profile
            if args.profile:
                profile = profiles_manager.get_profile(args.profile)
                if profile:
                    # Merge prompts (system first, then user's profile)
                    if profile.included_prompts:
                        profile_prompts = profile_prompts + profile.included_prompts
                    # User's strategy takes precedence
                    profile_strategy = profile.strategy
                    console.print(
                        f"Using profile: {args.profile} ({len(profile.included_prompts)} prompts)",
                        style=Colors.CYAN,
                    )
                else:
                    print_warning(
                        f"Profile '{args.profile}' not found. Run 'orun profiles' to see available profiles."
                    )

            # Resolve model

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

            # Merge profile prompts with command-line prompts
            initial_prompts = profile_prompts or []
            if args.use_prompt:
                initial_prompts.append(args.use_prompt)

            # Profile strategy can be overridden by command-line
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
                models_config.set_active_model(model_override)

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
                models_config.set_active_model(model_override)

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
        description="AI CLI wrapper for Ollama with powerful single-shot capabilities",
        epilog="""
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

Commands:
  chat              Start interactive chat session
  arxiv <query>     Search or fetch arXiv papers
  search <query>    Search the web (DuckDuckGo)
  fetch <url>       Fetch and display web content
  consensus         List available consensus pipelines
  consensus-config  Configure consensus pipelines
  models            List available models
  refresh           Sync models from Ollama
  shortcut          Change model shortcut
  set-active        Set active model
  history           List recent conversations
  prompts           List available prompt templates
  strategies        List available strategy templates
  c <id>            Continue conversation by ID
  last              Continue last conversation
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("prompt", nargs="*", help="Text prompt")
    parser.add_argument("-m", "--model", default="default", help="Model alias or name")
    parser.add_argument(
        "-i", "--images", nargs="*", type=str, help="Screenshot indices"
    )
    parser.add_argument(
        "-f",
        "--files",
        nargs="*",
        type=str,
        help="Files to include as context (supports glob patterns)",
    )
    parser.add_argument(
        "--dir", type=str, help="Directory to scan and include as context (recursive)"
    )
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
    parser.add_argument(
        "--system", type=str, help="Custom system prompt to guide the AI's behavior"
    )
    parser.add_argument(
        "--from-clipboard", action="store_true", help="Read input from clipboard"
    )
    parser.add_argument(
        "--to-clipboard", action="store_true", help="Copy output to clipboard"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        help="Model temperature (0.0-2.0, default: varies by model)",
    )
    parser.add_argument(
        "--top-p", type=float, help="Top-p sampling (0.0-1.0, default: varies by model)"
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Quiet mode: suppress progress messages",
    )
    parser.add_argument(
        "--yolo", action="store_true", help="Enable YOLO mode (no confirmations)"
    )
    parser.add_argument(
        "-C",
        "--consensus",
        type=str,
        metavar="PIPELINE",
        help="Use consensus pipeline instead of single model",
    )
    parser.add_argument(
        "--profile",
        dest="profile",
        help="Use a specific profile (included prompts)",
    )

    args = parser.parse_args()

    # Resolve Model
    model_name = None
    if args.model != "default":
        # User explicitly asked for a model
        model_name = models.get(args.model, args.model)
        # Update active model
        models_config.set_active_model(model_name)
    else:
        # User didn't specify, use active
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

    # Process file arguments
    file_paths = []
    if args.files:
        file_paths = utils.parse_file_patterns(args.files)

    # Process directory argument
    dir_context = None
    if args.dir:
        dir_context = utils.read_directory_context(args.dir)

    # Check for stdin input (pipe support)
    stdin_content = utils.read_stdin()

    # Check for clipboard input
    clipboard_content = None
    if args.from_clipboard:
        clipboard_content = utils.read_clipboard_text()

    # If no prompt/images/files/dir/stdin/clipboard provided, but have a prompt/strategy template or profile, show help
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

    # Build model options
    model_options = {}
    if args.temperature is not None:
        model_options["temperature"] = args.temperature
    if args.top_p is not None:
        model_options["top_p"] = args.top_p

    # Check if using consensus mode
    if args.consensus:
        # Use consensus pipeline instead of single model
        # Note: Some single-shot options may not apply to consensus
        if args.use_prompt or args.use_strategy:
            print_warning(
                "Warning: Prompt/strategy templates are not applied in consensus mode."
            )
            print_warning("Use system prompts in the pipeline configuration instead.")

        # Run consensus
        output = consensus.run_consensus(
            pipeline_name=args.consensus,
            user_prompt=user_prompt,
            image_paths=image_paths,
            system_prompt=args.system,
            tools_enabled=True,
            yolo_mode=args.yolo,
            model_options=model_options if model_options else None,
        )

        # Handle output options
        if args.output:
            utils.write_to_file(args.output, output)
        if args.to_clipboard:
            utils.copy_to_clipboard(output)
    else:
        # Load profile if specified
        # Always load system profile (can be overridden by user)
        system_profile = profiles_manager.get_profile("system")
        profile_prompts = system_profile.included_prompts if system_profile else []
        profile_strategy = None

        # Load user-specified profile and merge with system profile
        if args.profile:
            profile = profiles_manager.get_profile(args.profile)
            if profile:
                # Merge prompts (system first, then user's profile)
                if profile.included_prompts:
                    profile_prompts = profile_prompts + profile.included_prompts
                # User's strategy takes precedence
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

        # Merge profile prompts with command-line prompts
        merged_prompts = profile_prompts + (args.use_prompt or [])
        merged_strategy = args.use_strategy or (
            [profile_strategy] if profile_strategy else None
        )

        # Regular single-shot mode
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
