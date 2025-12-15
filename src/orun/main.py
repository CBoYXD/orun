import os
import glob
import argparse
import ollama
import sys

# --- CONFIGURATION ---
MODELS = {
    "s":          "llama3.1:8b",
    "search":     "qwen3:8b",
    "qwenvl":     "qwen3-vl:30b",
    "qwen":       "qwen3:30b",
    "coder":      "qwen3-coder:30b",
    "fast_coder": "qwen2.5-coder:14b",
    "gpt":        "gpt-oss:20b"
}
DEFAULT_MODEL = "llama3.1:8b"

SCREENSHOT_DIRS = [
    # os.path.expandvars(r"%USERPROFILE%\Pictures\Screenshots"),
    # os.path.expandvars(r"%USERPROFILE%\OneDrive\Pictures\Screenshots"),
    # os.path.expandvars(r"%USERPROFILE%\OneDrive\Зображення\Знімки екрана"),
    os.path.expandvars(r"C:\Users\Binar\Pictures\Screenshots"),
]

def get_screenshot_path(index):
    target_dir = next((d for d in SCREENSHOT_DIRS if os.path.exists(d)), None)
    if not target_dir:
        print("\033[91m⚠️ Screenshot folder not found!\033[0m")
        return None

    files = sorted(
        glob.glob(os.path.join(target_dir, "*.[pj][pn][g]*")),
        key=os.path.getmtime,
        reverse=True
    )

    if index > len(files):
        print(f"\033[91m⚠️ Screenshot #{index} not found.\033[0m")
        return None

    return files[index - 1]

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
        print() # Ensure a new line after the stream
    return full_response

def list_models(models_dict, default_model):
    """Prints all available models and their aliases in a formatted way."""
    print("\n\033[93mAvailable Models:\033[0m")
    max_alias_len = max(len(alias) for alias in models_dict.keys())
    
    for alias, model_name in models_dict.items():
        is_default = " (default)" if model_name == default_model else ""
        print(f"  \033[92m{alias:<{max_alias_len}}\033[0m : \033[94m{model_name}{is_default}\033[0m")
    
    print("\n\033[93mYou can use aliases with -m (e.g., -m coder).\033[0m")
    print(f"\033[93mIf -m is not specified, '{default_model}' is used.\033[0m")

def parse_image_indices(image_args):
    """
    Parses flexible image arguments.
    '3x' -> [1, 2, 3]
    '1,2,3' -> [1, 2, 3]
    '1 2 3' -> [1, 2, 3]
    Returns a list of unique, sorted integer indices.
    """
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
    try:
        stream = ollama.chat(
            model=model_name,
            messages=[{'role': 'user', 'content': user_prompt, 'images': image_paths or None}],
            stream=True,
        )
        handle_ollama_stream(stream)
    except Exception as e:
        print(f"\n\033[91m❌ Error: {e}\033[0m")

def run_chat_mode(model_name, initial_prompt, initial_images):
    """Runs an interactive chat session."""
    print(f"\033[92mEntering chat mode with '{model_name}'.\033[0m")
    print("Type 'quit' or 'exit' to end the session.")
    messages = []

    if initial_prompt or initial_images:
        if not initial_prompt:
            initial_prompt = "Describe this image."
        
        print(f"\033[96m🤖 [{model_name}] Thinking...\033[0m")
        print("\033[94mAssistant: \033[0m", end="")
        
        user_message = {'role': 'user', 'content': initial_prompt, 'images': initial_images or None}
        messages.append(user_message)
        
        try:
            stream = ollama.chat(model=model_name, messages=messages, stream=True)
            assistant_response = handle_ollama_stream(stream)
            if assistant_response:
                messages.append({'role': 'assistant', 'content': assistant_response})
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
            
            stream = ollama.chat(model=model_name, messages=messages, stream=True)
            assistant_response = handle_ollama_stream(stream)
            if assistant_response:
                messages.append({'role': 'assistant', 'content': assistant_response})
            else:
                messages.pop()

        except EOFError:
            break
        except Exception as e:
            print(f"\n\033[91m❌ Error: {e}\033[0m")
            if messages and messages[-1]['role'] == 'user':
                messages.pop()

def main():
    parser = argparse.ArgumentParser(description="AI CLI wrapper")
    parser.add_argument("prompt", nargs="*", help="Text prompt")
    parser.add_argument("-m", "--model", default="default", help="Model alias or name")
    parser.add_argument("-i", "--images", nargs="*", type=str, help="Screenshot indices. Examples: '1 2', '1,2,3', '3x' (last 3). Default: 1.")
    parser.add_argument("--chat", action="store_true", help="Enable continuous chat mode")
    parser.add_argument("--list-models", action="store_true", help="List all available models and their aliases.")
    
    args = parser.parse_args()

    if args.list_models:
        list_models(MODELS, DEFAULT_MODEL)
        return

    target_model_key = args.model if args.model != "default" else DEFAULT_MODEL
    model_name = MODELS.get(target_model_key, target_model_key)

    user_prompt = " ".join(args.prompt)
    image_paths = []
    
    if args.images is not None:
        if not args.images: # Handles '-i' with no arguments
            indices = [1]
        else:
            indices = parse_image_indices(args.images)
        
        for idx in indices:
            path = get_screenshot_path(idx)
            if path:
                image_paths.append(path)
                print(f"\033[90m🖼️  Added: {os.path.basename(path)}\033[0m")

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