import sys
import os
import functools
from pathlib import Path

class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GREY = "\033[90m"
    RESET = "\033[0m"

def colored(text: str, color: str) -> str:
    """Wraps text in color codes."""
    return f"{color}{text}{Colors.RESET}"

def print_error(msg: str):
    print(colored(f"❌ {msg}", Colors.RED))

def print_success(msg: str):
    print(colored(f"✅ {msg}", Colors.GREEN))

def print_warning(msg: str):
    print(colored(f"⚠️ {msg}", Colors.YELLOW))

def print_info(msg: str):
    print(colored(msg, Colors.CYAN))

def handle_cli_errors(func):
    """Decorator to handle KeyboardInterrupt and general exceptions gracefully."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            sys.exit(0)
        except Exception as e:
            print() # Newline
            print_error(f"An unexpected error occurred: {e}")
            sys.exit(1)
    return wrapper

# Configuration
SCREENSHOT_DIRS = [
    Path.home() / "Pictures" / "Screenshots",
    Path.home() / "Pictures"
]

def setup_console():
    """Configures the console for proper emoji support on Windows."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def get_screenshot_path(index: int) -> str | None:
    """Finds a screenshot by index (1-based, newest first)."""
    target_dir = next((d for d in SCREENSHOT_DIRS if d.exists()), None)
    if not target_dir:
        print_error("Screenshot folder not found!")
        return None

    files = []
    for ext in ["*.png", "*.jpg", "*.jpeg"]:
        files.extend(target_dir.glob(ext))

    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    if index > len(files):
        print_error(f"Screenshot #{index} not found.")
        return None

    return str(files[index - 1])

def parse_image_indices(image_args: list[str]) -> list[int]:
    """Parses flexible image arguments (e.g., '1', '1,2', '3x')."""
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
                print_error(f"Invalid range format: '{arg}'")
        elif ',' in arg:
            parts = arg.split(',')
            for part in parts:
                try:
                    indices.add(int(part))
                except ValueError:
                    print_error(f"Invalid index: '{part}' in '{arg}'")
        else:
            try:
                indices.add(int(arg))
            except ValueError:
                print_error(f"Invalid index: '{arg}'")

    return sorted(list(indices))

def get_image_paths(image_args: list[str] | None) -> list[str]:
    """Resolves image arguments to file paths."""
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
                print(colored(f"🖼️  Added: {os.path.basename(path)}", Colors.GREY))
    return image_paths
