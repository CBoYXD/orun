import sys
import argparse
import os

from orun import db, commands, utils, core
from orun.utils import Colors, colored, print_error, print_warning

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
                print_warning("Usage: orun shortcut <model_name_or_shortcut> <new_shortcut>")
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
            parser.add_argument("-n", type=int, default=10, help="Number of conversations to show")
            args = parser.parse_args(sys.argv[2:])
            commands.cmd_history(args.n)
            return

        if cmd == "chat":
            parser = argparse.ArgumentParser(prog="orun chat")
            parser.add_argument("prompt", nargs="*", help="Initial prompt")
            parser.add_argument("-m", "--model", help="Override model")
            parser.add_argument("-i", "--images", nargs="*", type=str, help="Screenshot indices")
            parser.add_argument("--yolo", action="store_true", help="Enable YOLO mode (no confirmations)")
            args = parser.parse_args(sys.argv[2:])

            image_paths = utils.get_image_paths(args.images)

            # Resolve model
            model_name = models.get(args.model, args.model) if args.model else db.get_active_model()

            if not model_name:
                print_error("No active model set.")
                print(f"Please specify a model with {colored('-m <model>', Colors.YELLOW)} or set a default with {colored('orun set-active <model>', Colors.YELLOW)}")
                return

            if args.model:
                db.set_active_model(model_name)

            core.run_chat_mode(model_name, " ".join(args.prompt) if args.prompt else None, image_paths, use_tools=True)
            return

        if cmd == "c":
            parser = argparse.ArgumentParser(prog="orun c")
            parser.add_argument("id", type=int, help="Conversation ID")
            parser.add_argument("prompt", nargs="*", help="Initial prompt")
            parser.add_argument("-m", "--model", help="Override model")
            parser.add_argument("-i", "--images", nargs="*", type=str, help="Screenshot indices")
            parser.add_argument("--yolo", action="store_true", help="Enable YOLO mode (no confirmations)")
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
            commands.cmd_continue(args.id, " ".join(args.prompt) if args.prompt else None, image_paths, model_override, use_tools=True, yolo=args.yolo)
            return

        if cmd == "last":
            parser = argparse.ArgumentParser(prog="orun last")
            parser.add_argument("prompt", nargs="*", help="Initial prompt")
            parser.add_argument("-m", "--model", help="Override model")
            parser.add_argument("-i", "--images", nargs="*", type=str, help="Screenshot indices")
            parser.add_argument("--yolo", action="store_true", help="Enable YOLO mode (no confirmations)")
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
            commands.cmd_last(" ".join(args.prompt) if args.prompt else None, image_paths, model_override, use_tools=True, yolo=args.yolo)
            return

    # Default Query Mode (Single Shot)
    parser = argparse.ArgumentParser(
        description="AI CLI wrapper for Ollama",
        usage="orun [command] [prompt] [options]\n\nCommands:\n  chat        Start interactive chat session\n  models      List available models\n  refresh     Sync models from Ollama\n  shortcut    Change model shortcut\n  set-active  Set active model\n  history     List recent conversations\n  c <id>      Continue conversation by ID\n  last        Continue last conversation"
    )
    parser.add_argument("prompt", nargs="*", help="Text prompt")
    parser.add_argument("-m", "--model", default="default", help="Model alias or name")
    parser.add_argument("-i", "--images", nargs="*", type=str, help="Screenshot indices")
    parser.add_argument("--yolo", action="store_true", help="Enable YOLO mode (no confirmations)")

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
        print_error("No active model set.")
        print(f"Please specify a model with {colored('-m <model>', Colors.YELLOW)} or set a default with {colored('orun set-active <model>', Colors.YELLOW)}")
        return

    user_prompt = " ".join(args.prompt) if args.prompt else ""
    image_paths = utils.get_image_paths(args.images)

    # If no prompt/images provided, show help
    if not user_prompt and not image_paths:
        parser.print_help()
        return

    # Always enable tools for single shot too
    core.run_single_shot(model_name, user_prompt, image_paths, use_tools=True, yolo=args.yolo)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
