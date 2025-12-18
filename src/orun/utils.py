import datetime
import functools
import os
import subprocess
import sys
import time
from pathlib import Path

import ollama
from PIL import Image, ImageGrab

from .rich_utils import Colors, console, print_error, print_info, print_success, print_warning


def ensure_ollama_running():
    """Checks if Ollama is running and attempts to start it if not."""
    try:
        # Quick check with a short timeout to avoid hanging if server is weird
        # ollama.list() doesn't support timeout natively in the python client usually,
        # but it uses httpx, so it might fail fast if port is closed.
        ollama.list()
        return
    except Exception:
        print_warning("Ollama is not running.")
        print_info("Attempting to start Ollama server...")

        try:
            # Start in background
            if sys.platform == "win32":
                # Using shell=True and 'start' command to detach properly on Windows
                subprocess.Popen(
                    "start /B ollama serve",
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

            # Wait for it to become ready
            console.print("Waiting for Ollama to start...", style=Colors.DIM, end="")
            for _ in range(5):  # Wait up to 5 seconds (reduced from 10)
                try:
                    time.sleep(1)
                    ollama.list()
                    console.print()  # Newline
                    console.print("Ollama started successfully.", style=Colors.GREEN)
                    return
                except Exception:
                    console.print(".", end="", flush=True)

            console.print()
            console.print("Timed out waiting for Ollama to start.", style=Colors.RED)
            console.print(
                "Please start Ollama manually (run 'ollama serve' or open the app).",
                style=Colors.INFO,
            )
            sys.exit(1)

        except FileNotFoundError:
            print_error("Ollama executable not found in PATH.")
            print_info("Please install Ollama from https://ollama.com/")
            sys.exit(1)
        except Exception as e:
            print_error(f"Failed to start Ollama: {e}")
            sys.exit(1)


def handle_cli_errors(func):
    """Decorator to handle KeyboardInterrupt and general exceptions gracefully."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            console.print("\n\n👋 Goodbye!", style=Colors.GREY)
            sys.exit(0)
        except Exception as e:
            console.print()  # Newline
            print_error(f"An unexpected error occurred: {e}")
            sys.exit(1)

    return wrapper


# Configuration
SCREENSHOT_DIRS = [Path.home() / "Pictures" / "Screenshots", Path.home() / "Pictures"]


def setup_console():
    """Configures the console for proper emoji support on Windows."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


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
        if "x" in arg:
            try:
                count = int(arg.replace("x", ""))
                indices.update(range(1, count + 1))
            except ValueError:
                print_error(f"Invalid range format: '{arg}'")
        elif "," in arg:
            parts = arg.split(",")
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
                console.print(f"🖼️  Added: {os.path.basename(path)}", style=Colors.DIM)
    return image_paths


def save_clipboard_image() -> str | None:
    """
    Saves an image from the clipboard to a temporary file.
    Returns the file path if successful, None if no image in clipboard.
    """
    try:
        # Get image from clipboard
        clipboard_content = ImageGrab.grabclipboard()

        if clipboard_content is None:
            return None

        # Handle different clipboard content types
        image = None

        # Check if it's already a PIL Image
        if isinstance(clipboard_content, Image.Image):
            image = clipboard_content
        # Check if it's a list of file paths (Windows file copy)
        elif isinstance(clipboard_content, list):
            # Try to open the first file if it's an image
            try:
                first_file = Path(clipboard_content[0])
                if first_file.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                    image = Image.open(first_file)
            except:
                return None
        else:
            # Unknown format
            return None

        if image is None:
            return None

        # Create temp directory if it doesn't exist
        temp_dir = Path.home() / ".orun" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"clipboard_{timestamp}.png"
        filepath = temp_dir / filename

        # Convert to RGB if needed (for RGBA or other modes)
        if image.mode in ('RGBA', 'LA', 'P'):
            # Convert RGBA to RGB with white background
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')

        # Save image
        image.save(filepath, "PNG")

        console.print(f"📋 Saved clipboard image: {filename}", style=Colors.GREEN)
        return str(filepath)

    except Exception as e:
        # Silently fail - no image in clipboard
        return None


def read_file_context(file_paths: list[str]) -> str:
    """Reads multiple files and formats them as context for the AI."""
    if not file_paths:
        return ""

    context_parts = []
    for file_path in file_paths:
        try:
            path = Path(file_path)
            if not path.exists():
                print_error(f"File not found: {file_path}")
                continue

            if not path.is_file():
                print_error(f"Not a file: {file_path}")
                continue

            # Read file content
            try:
                content = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                # Try with latin-1 as fallback
                try:
                    content = path.read_text(encoding='latin-1')
                except Exception as e:
                    print_error(f"Could not read {file_path}: {e}")
                    continue

            context_parts.append(f"--- File: {file_path} ---\n{content}\n")
            console.print(f"📄 Added file: {file_path}", style=Colors.DIM)

        except Exception as e:
            print_error(f"Error reading {file_path}: {e}")

    if context_parts:
        return "\n".join(context_parts)
    return ""


def parse_file_patterns(file_args: list[str]) -> list[str]:
    """Expands file patterns (globs) to actual file paths."""
    import glob as glob_module

    if not file_args:
        return []

    expanded_paths = []
    for pattern in file_args:
        # Support glob patterns
        matches = glob_module.glob(pattern, recursive=True)
        if matches:
            expanded_paths.extend(matches)
        else:
            # Not a pattern, treat as literal path
            expanded_paths.append(pattern)

    # Remove duplicates while preserving order
    seen = set()
    unique_paths = []
    for path in expanded_paths:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)

    return unique_paths
