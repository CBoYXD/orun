import os
import argparse
import ollama
import sys
from pathlib import Path

from orun import db

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')



SCREENSHOT_DIRS = [
    Path.home() / "Pictures" / "Screenshots",
    Path.home() / "Pictures"
]

def get_screenshot_path(index):
    target_dir = next((d for d in SCREENSHOT_DIRS if d.exists()), None)
    if not target_dir:
        print("\033[91m⚠️ Screenshot folder not found!\033[0m")
        return None

    files = []
    for ext in ["*.png", "*.jpg", "*.jpeg"]:
        files.extend(target_dir.glob(ext))

    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    if index > len(files):
        print(f"\033[91m⚠️ Screenshot #{index} not found.\033[0m")
        return None

    return str(files[index - 1])

def handle_ollama_stream(stream):
    """Prints the stream and returns the full response."""
    full_response = ""
    try:
        for chunk in stream:
            content = chunk['message']['content']
            print(content, end='', flush=True)
            full_response += content
    except Exception as e:
        print(f"\n\033[91m❌ Stream Error: {e}\033[0m")
    finally:
        print()
    return full_response

def cmd_models():
    """Prints all available models and their aliases."""
    models = db.get_models()
    active_model = db.get_active_model()
    
    print("\n\033[93mAvailable Models:\033[0m")
    if not models:
        print("  No models found.")
        return

    max_alias_len = max(len(alias) for alias in models.keys())

    for alias, model_name in models.items():
        marker = ""
        if model_name == active_model:
            marker = " \033[95m(active)\033[0m"

            
        print(f"  \033[92m{alias:<{max_alias_len}}\033[0m : \033[94m{model_name}{marker}\033[0m")

    print("\n\033[93mUse -m <alias> to select a model.\033[0m")

def cmd_history(limit: int = 10):
    """Prints recent conversations."""
    conversations = db.get_recent_conversations(limit)
    if not conversations:
        print("\033[93mNo conversations found.\033[0m")
        return

    print("\n\033[93mRecent Conversations:\033[0m")
    for conv in conversations:
        messages = db.get_conversation_messages(conv["id"])
        first_msg = messages[0]["content"][:50] + "..." if messages and len(messages[0]["content"]) > 50 else (messages[0]["content"] if messages else "Empty")
        print(f"  \033[92m{conv['id']:>3}\033[0m | \033[94m{conv['model']:<20}\033[0m | {first_msg}")

    print("\n\033[93mUse 'orun c <id>' to continue a conversation.\033[0m")

def cmd_continue(conversation_id: int, prompt: str = None, image_paths: list = None, model_override: str = None):
    """Continue an existing conversation."""
    conv = db.get_conversation(conversation_id)
    if not conv:
        print(f"\033[91m❌ Conversation #{conversation_id} not found.\033[0m")
        return

    model_name = model_override if model_override else conv["model"]
    run_chat_mode(model_name, prompt or "", image_paths or [], conversation_id)

def cmd_last(prompt: str = None, image_paths: list = None, model_override: str = None):
    """Continue the last conversation."""
    conversation_id = db.get_last_conversation_id()
    if not conversation_id:
        print("\033[91m❌ No conversations found.\033[0m")
        return

    cmd_continue(conversation_id, prompt, image_paths, model_override)

def parse_image_indices(image_args):
    """Parses flexible image arguments."""
    indices = set()
    if not image_args:
        return []

    for arg in image_args:
        arg = str(arg).lower()
        if 'x' in arg:
            try:
                count = int(arg.replace('x', ''))
                indices.update(range(1, count + 1))
            except ValueError:
                print(f"\033[91m⚠️ Invalid range format: '{arg}'\033[0m")
        elif ',' in arg:
            parts = arg.split(',')
            for part in parts:
                try:
                    indices.add(int(part))
                except ValueError:
                    print(f"\033[91m⚠️ Invalid index: '{part}' in '{arg}'\033[0m")
        else:
            try:
                indices.add(int(arg))
            except ValueError:
                print(f"\033[91m⚠️ Invalid index: '{arg}'\033[0m")

    return sorted(list(indices))

def run_single_shot(model_name, user_prompt, image_paths):
    """Handles a single query to the model."""
    print(f"\033[96m🤖 [{model_name}] Thinking...\033[0m")

    conversation_id = db.create_conversation(model_name)
    db.add_message(conversation_id, "user", user_prompt, image_paths or None)

    try:
        stream = ollama.chat(
            model=model_name,
            messages=[{'role': 'user', 'content': user_prompt, 'images': image_paths or None}],
            stream=True,
        )
        response = handle_ollama_stream(stream)
        if response:
            db.add_message(conversation_id, "assistant", response)
    except Exception as e:
        print(f"\n\033[91m❌ Error: {e}\033[0m")

def run_chat_mode(model_name, initial_prompt, initial_images, conversation_id=None):
    """Runs an interactive chat session."""
    print(f"\033[92mEntering chat mode with '{model_name}'.\033[0m")
    print("Type 'quit' or 'exit' to end the session.")

    if conversation_id:
        messages = db.get_conversation_messages(conversation_id)
        print(f"\033[90mLoaded {len(messages)} messages from conversation #{conversation_id}\033[0m")
    else:
        messages = []
        conversation_id = db.create_conversation(model_name)

    if initial_prompt or initial_images:
        if not initial_prompt:
            initial_prompt = "Describe this image."

        print(f"\033[96m🤖 [{model_name}] Thinking...\033[0m")
        print("\033[94mAssistant: \033[0m", end="")

        user_message = {'role': 'user', 'content': initial_prompt, 'images': initial_images or None}
        messages.append(user_message)
        db.add_message(conversation_id, "user", initial_prompt, initial_images or None)

        try:
            stream = ollama.chat(model=model_name, messages=messages, stream=True)
            assistant_response = handle_ollama_stream(stream)
            if assistant_response:
                messages.append({'role': 'assistant', 'content': assistant_response})
                db.add_message(conversation_id, "assistant", assistant_response)
        except Exception as e:
            print(f"\n\033[91m❌ Error: {e}\033[0m")
            messages.pop()

    while True:
        try:
            user_input = input("\n\033[92mYou: \033[0m")
            if user_input.lower() in ['quit', 'exit']:
                break

            print(f"\033[96m🤖 [{model_name}] Thinking...\033[0m")
            print("\033[94mAssistant: \033[0m", end="")

            messages.append({'role': 'user', 'content': user_input})
            db.add_message(conversation_id, "user", user_input)

            stream = ollama.chat(model=model_name, messages=messages, stream=True)
            assistant_response = handle_ollama_stream(stream)
            if assistant_response:
                messages.append({'role': 'assistant', 'content': assistant_response})
                db.add_message(conversation_id, "assistant", assistant_response)
            else:
                messages.pop()

        except EOFError:
            break
        except Exception as e:
            print(f"\n\033[91m❌ Error: {e}\033[0m")
            if messages and messages[-1]['role'] == 'user':
                messages.pop()

def get_image_paths(image_args):
    """Parse image arguments and return list of paths."""
    image_paths = []
    if image_args is not None:
        if not image_args:
            indices = [1]
        else:
            indices = parse_image_indices(image_args)

        for idx in indices:
            path = get_screenshot_path(idx)
            if path:
                image_paths.append(path)
                print(f"\033[90m🖼️  Added: {os.path.basename(path)}\033[0m")
    return image_paths

def main():
    # Initialize DB
    db.initialize()
    

    models = db.get_models()

    # Check for subcommands first
    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "models":
            cmd_models()
            return

        if cmd == "refresh":
            print("\033[96m🔄 Syncing models from Ollama...\033[0m")
            db.refresh_ollama_models()
            return

        if cmd == "shortcut":
            if len(sys.argv) < 4:
                print("\033[91m⚠️ Usage: orun shortcut <model_name_or_shortcut> <new_shortcut>\033[0m")
                return
            identifier = sys.argv[2]
            new_shortcut = sys.argv[3]
            if db.update_model_shortcut(identifier, new_shortcut):
                print(f"\033[92m✅ Shortcut updated: {new_shortcut} -> {identifier} (or resolved full name)\033[0m")
            else:
                print(f"\033[91m❌ Could not update shortcut. Model '{identifier}' not found or shortcut '{new_shortcut}' already taken.\033[0m")
            return

        if cmd == "set-active":
            if len(sys.argv) < 3:
                print("\033[91m⚠️ Usage: orun set-active <model_name_or_shortcut>\033[0m")
                return
            target = sys.argv[2]
            db.set_active_model(target)
            active = db.get_active_model()
            if active:
                 print(f"\033[92m✅ Active model set to: {active}\033[0m")
            else:
                 print(f"\033[91m❌ Could not set active model. '{target}' not found.\033[0m")
            return

        if cmd == "history":
            parser = argparse.ArgumentParser(prog="orun history")
            parser.add_argument("-n", type=int, default=10, help="Number of conversations to show")
            args = parser.parse_args(sys.argv[2:])
            cmd_history(args.n)
            return

        if cmd == "c":
            parser = argparse.ArgumentParser(prog="orun c")
            parser.add_argument("id", type=int, help="Conversation ID")
            parser.add_argument("prompt", nargs="*", help="Initial prompt")
            parser.add_argument("-m", "--model", help="Override model")
            parser.add_argument("-i", "--images", nargs="*", type=str, help="Screenshot indices")
            args = parser.parse_args(sys.argv[2:])
            image_paths = get_image_paths(args.images)
            
            # Resolve model
            model_override = models.get(args.model, args.model) if args.model else None
            
            # We need to peek at the conversation to know the model if not overridden
            if not model_override:
                conv = db.get_conversation(args.id)
                if conv:
                     model_override = conv["model"]
            
            if model_override:
                db.set_active_model(model_override)

            cmd_continue(args.id, " ".join(args.prompt) if args.prompt else None, image_paths, model_override)
            return

        if cmd == "last":
            parser = argparse.ArgumentParser(prog="orun last")
            parser.add_argument("prompt", nargs="*", help="Initial prompt")
            parser.add_argument("-m", "--model", help="Override model")
            parser.add_argument("-i", "--images", nargs="*", type=str, help="Screenshot indices")
            args = parser.parse_args(sys.argv[2:])
            image_paths = get_image_paths(args.images)
            
            # Resolve model
            model_override = models.get(args.model, args.model) if args.model else None
            
            if not model_override:
                 cid = db.get_last_conversation_id()
                 if cid:
                     conv = db.get_conversation(cid)
                     if conv:
                         model_override = conv["model"]
            
            if model_override:
                db.set_active_model(model_override)

            cmd_last(" ".join(args.prompt) if args.prompt else None, image_paths, model_override)
            return

    # Default query mode
    parser = argparse.ArgumentParser(
        description="AI CLI wrapper for Ollama",
        usage="orun [command] [prompt] [options]\n\nCommands:\n  models      List available models\n  refresh     Sync models from Ollama\n  shortcut    Change model shortcut\n  set-active  Set active model\n  history     List recent conversations\n  c <id>      Continue conversation by ID\n  last        Continue last conversation"
    )
    parser.add_argument("prompt", nargs="*", help="Text prompt")
    parser.add_argument("-m", "--model", default="default", help="Model alias or name")
    parser.add_argument("-i", "--images", nargs="*", type=str, help="Screenshot indices")
    parser.add_argument("--chat", action="store_true", help="Enable chat mode")

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
        print("\033[91m❌ No active model set.\033[0m")
        print("Please specify a model with \033[93m-m <model>\033[0m or set a default with \033[93morun set-active <model>\033[0m")
        return

    user_prompt = " ".join(args.prompt) if args.prompt else ""
    image_paths = get_image_paths(args.images)

    if not args.chat and not user_prompt and not image_paths:
        parser.print_help()
        return

    if args.chat:
        run_chat_mode(model_name, user_prompt, image_paths)
    else:
        if not user_prompt and image_paths:
            user_prompt = "Describe this image."
        run_single_shot(model_name, user_prompt, image_paths)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)