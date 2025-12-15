import functools
import os
import subprocess
import sys
import time
from pathlib import Path
import html

import ollama
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import HTML


class Colors:
    RED = "ansired"
    GREEN = "ansigreen"
    YELLOW = "ansiyellow"
    BLUE = "ansiblue"
    MAGENTA = "ansimagenta"
    CYAN = "ansicyan"
    GREY = "ansigray" # 'gray' or 'brightblack' depending on PT version, 'ansigray' works usually or 'gray'
    # prompt_toolkit uses 'gray' or '#888888'. Let's use 'gray'.
    RESET = "" # Not needed for HTML tags, closing tag handles it


def colored(text: str, color: str) -> str:
    """Wraps text in HTML color tags for prompt_toolkit."""
    if color == Colors.GREY:
        color = "gray" # fix map
    return f"<{color}>{html.escape(str(text))}</{color}>"


def print_error(msg: str):
    print_formatted_text(HTML(colored(f"❌ {msg}", Colors.RED)))


def print_success(msg: str):
    print_formatted_text(HTML(colored(f"✅ {msg}", Colors.GREEN)))


def print_warning(msg: str):
    print_formatted_text(HTML(colored(f"⚠️ {msg}", Colors.YELLOW)))


def print_info(msg: str):
    print_formatted_text(HTML(colored(msg, Colors.CYAN)))


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
            print_formatted_text(
                HTML(colored("Waiting for Ollama to start...", Colors.GREY)),
                end="",
                flush=True,
            )
            for _ in range(5):  # Wait up to 5 seconds (reduced from 10)
                try:
                    time.sleep(1)
                    ollama.list()
                    print()  # Newline
                    print_success("Ollama started successfully.")
                    return
                except Exception:
                    print(".", end="", flush=True)

            print()
            print_error("Timed out waiting for Ollama to start.")
            print_info(
                "Please start Ollama manually (run 'ollama serve' or open the app)."
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
            print("\n\n👋 Goodbye!")
            sys.exit(0)
        except Exception as e:
            print()  # Newline
            print_error(f"An unexpected error occurred: {e}")
            sys.exit(1)

    return wrapper


# Configuration
SCREENSHOT_DIRS = [Path.home() / "Pictures" / "Screenshots", Path.home() / "Pictures"]


def setup_console():
    """Configures the console for proper emoji support on Windows."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


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
                print_formatted_text(HTML(colored(f"🖼️  Added: {os.path.basename(path)}", Colors.GREY)))
    return image_paths
