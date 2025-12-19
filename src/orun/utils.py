import datetime
import functools
import glob
import os
import subprocess
import sys
import time
from pathlib import Path

import ollama
from PIL import Image, ImageGrab

from orun.rich_utils import Colors, console, print_error, print_info, print_warning


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


def ensure_function_gemma_available(auto_download: bool = True) -> bool:
    """
    Check if FunctionGemma model is available in Ollama.
    Optionally download it if not found.

    Args:
        auto_download: If True, automatically download FunctionGemma if missing

    Returns:
        True if FunctionGemma is available, False otherwise
    """
    try:
        # Handle different response types (object vs dict)
        response = ollama.list()
        if hasattr(response, "models"):
            models = response.models
        elif isinstance(response, dict):
            models = response.get("models", [])
        else:
            models = []

        function_model_found = False
        for model in models:
            # Handle model item types
            name = ""
            if hasattr(model, "model"):
                name = model.model
            elif hasattr(model, "name"):
                name = model.name
            elif isinstance(model, dict):
                name = model.get("model", model.get("name", ""))

            if "functiongemma" in name.lower():
                function_model_found = True
                break

        if function_model_found:
            return True

        if not auto_download:
            return False

        # Ask user if they want to download
        console.print("\n[yellow]FunctionGemma model not found.[/yellow]")
        console.print(
            "[dim]FunctionGemma is a specialized 270m model optimized for tool calling.[/dim]"
        )
        console.print("[dim]It will significantly improve tool usage accuracy.[/dim]\n")

        response = (
            console.input(
                "[cyan]Download FunctionGemma 270m model? (~270MB) [Y/n]: [/cyan]"
            )
            .lower()
            .strip()
        )

        if response and response not in ["y", "yes"]:
            console.print(
                "[yellow]FunctionGemma delegation disabled. Using direct tool calling.[/yellow]"
            )
            return False

        # Download the model
        console.print("\n[cyan]Downloading functiongemma:270m...[/cyan]")
        console.print("[dim]This may take a few minutes...[/dim]\n")

        try:
            # Use ollama pull to download
            result = subprocess.run(
                ["ollama", "pull", "functiongemma:270m"],
                capture_output=False,
                text=True,
            )

            if result.returncode == 0:
                console.print(
                    "\n[green]✓ FunctionGemma downloaded successfully![/green]"
                )
                return True
            else:
                print_error("Failed to download FunctionGemma")
                return False

        except Exception as e:
            print_error(f"Error downloading FunctionGemma: {e}")
            return False

    except Exception as e:
        print_warning(f"Could not check for FunctionGemma: {e}")
        return False


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
                if first_file.suffix.lower() in [
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".bmp",
                ]:
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
        if image.mode in ("RGBA", "LA", "P"):
            # Convert RGBA to RGB with white background
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(
                image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None
            )
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Save image
        image.save(filepath, "PNG")

        console.print(f"📋 Saved clipboard image: {filename}", style=Colors.GREEN)
        return str(filepath)

    except Exception:
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
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Try with latin-1 as fallback
                try:
                    content = path.read_text(encoding="latin-1")
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
    if not file_args:
        return []

    expanded_paths = []
    for pattern in file_args:
        # Support glob patterns
        matches = glob.glob(pattern, recursive=True)
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


def read_stdin() -> str | None:
    """Reads input from stdin if available (for pipe support)."""
    # Check if stdin is a pipe (not a TTY)
    if not sys.stdin.isatty():
        try:
            stdin_content = sys.stdin.read()
            if stdin_content:
                console.print("📥 Read input from stdin", style=Colors.DIM)
                return stdin_content
        except Exception as e:
            print_error(f"Error reading stdin: {e}")
    return None


def read_clipboard_text() -> str | None:
    """Reads text content from clipboard."""
    try:
        # Try using ImageGrab first (it can also get text on some platforms)
        # On Windows, use PowerShell to get clipboard text
        if sys.platform == "win32":
            try:
                result = subprocess.run(
                    ["powershell", "-command", "Get-Clipboard"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    console.print("📋 Read text from clipboard", style=Colors.DIM)
                    return result.stdout.strip()
            except Exception:
                pass

        # On Linux/Mac, try xclip/pbpaste
        elif sys.platform == "darwin":  # macOS
            try:
                result = subprocess.run(
                    ["pbpaste"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    console.print("📋 Read text from clipboard", style=Colors.DIM)
                    return result.stdout.strip()
            except Exception:
                pass
        else:  # Linux
            try:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    console.print("📋 Read text from clipboard", style=Colors.DIM)
                    return result.stdout.strip()
            except Exception:
                pass

        return None
    except Exception:
        return None


def write_clipboard_text(text: str) -> bool:
    """Writes text content to clipboard."""
    try:
        # On Windows, use PowerShell to set clipboard
        if sys.platform == "win32":
            try:
                process = subprocess.Popen(
                    ["powershell", "-command", "Set-Clipboard"],
                    stdin=subprocess.PIPE,
                    text=True,
                )
                process.communicate(input=text, timeout=5)
                if process.returncode == 0 or process.returncode is None:
                    console.print("📋 Copied to clipboard", style=Colors.GREEN)
                    return True
            except Exception:
                pass

        # On macOS, use pbcopy
        elif sys.platform == "darwin":
            try:
                process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, text=True)
                process.communicate(input=text, timeout=5)
                if process.returncode == 0 or process.returncode is None:
                    console.print("📋 Copied to clipboard", style=Colors.GREEN)
                    return True
            except Exception:
                pass

        # On Linux, try xclip
        else:
            try:
                process = subprocess.Popen(
                    ["xclip", "-selection", "clipboard"],
                    stdin=subprocess.PIPE,
                    text=True,
                )
                process.communicate(input=text, timeout=5)
                if process.returncode == 0 or process.returncode is None:
                    console.print("📋 Copied to clipboard", style=Colors.GREEN)
                    return True
            except Exception:
                pass

        print_error("Failed to copy to clipboard")
        return False
    except Exception as e:
        print_error(f"Error writing to clipboard: {e}")
        return False


def scan_project_context(path: str = ".", max_files: int = 30) -> str:
    """
    Scan a project directory and build a context summary.
    Includes: README, structure, key config files.
    """
    try:
        project_path = Path(path).resolve()
        if not project_path.exists():
            return f"Error: Path '{path}' does not exist"

        context_parts = []

        # Project name
        context_parts.append(f"# Project: {project_path.name}")
        context_parts.append(f"Path: {project_path}\n")

        # Check for README
        readme_files = ["README.md", "README.rst", "README.txt", "README"]
        for readme in readme_files:
            readme_path = project_path / readme
            if readme_path.exists():
                try:
                    content = readme_path.read_text(encoding="utf-8", errors="ignore")
                    if len(content) > 5000:
                        content = content[:5000] + "\n... (truncated)"
                    context_parts.append(f"## README\n\n{content}\n")
                    break
                except Exception:
                    pass

        # Check for key config files
        config_files = [
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "requirements.txt",
            "setup.py",
            "Makefile",
            "justfile",
            ".env.example",
            "docker-compose.yml",
            "Dockerfile",
        ]
        found_configs = []
        for config in config_files:
            config_path = project_path / config
            if config_path.exists():
                found_configs.append(config)

        if found_configs:
            context_parts.append(f"## Config Files Found\n{', '.join(found_configs)}\n")

        # Directory structure (limited depth)
        context_parts.append("## Directory Structure\n```")

        exclude_dirs = {
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            "dist",
            "build",
            ".cache",
            ".pytest_cache",
            "target",
            ".ruff_cache",
            ".mypy_cache",
            "eggs",
            ".eggs",
        }

        def tree(dir_path: Path, prefix: str = "", depth: int = 0, max_depth: int = 3):
            if depth > max_depth:
                return []
            lines = []
            try:
                items = sorted(
                    dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())
                )
                dirs = [
                    i
                    for i in items
                    if i.is_dir()
                    and i.name not in exclude_dirs
                    and not i.name.startswith(".")
                ]
                files = [i for i in items if i.is_file() and not i.name.startswith(".")]

                # Limit items per level
                dirs = dirs[:10]
                files = files[:15]

                for d in dirs:
                    lines.append(f"{prefix}{d.name}/")
                    lines.extend(tree(d, prefix + "  ", depth + 1, max_depth))

                for f in files:
                    lines.append(f"{prefix}{f.name}")

            except PermissionError:
                pass
            return lines

        tree_lines = tree(project_path)
        context_parts.append("\n".join(tree_lines[:100]))  # Limit to 100 lines
        context_parts.append("```\n")

        # Key source files summary
        source_extensions = {
            ".py",
            ".js",
            ".ts",
            ".go",
            ".rs",
            ".java",
            ".c",
            ".cpp",
            ".h",
        }
        source_files = []
        for ext in source_extensions:
            source_files.extend(project_path.rglob(f"*{ext}"))
            if len(source_files) > 50:
                break

        # Filter out excluded dirs
        source_files = [
            f for f in source_files if not any(ex in str(f) for ex in exclude_dirs)
        ][:30]

        if source_files:
            context_parts.append(f"## Source Files ({len(source_files)} found)\n")
            for sf in source_files[:20]:
                rel_path = sf.relative_to(project_path)
                context_parts.append(f"- {rel_path}")
            if len(source_files) > 20:
                context_parts.append(f"- ... and {len(source_files) - 20} more")
            context_parts.append("")

        return "\n".join(context_parts)

    except Exception as e:
        return f"Error scanning project: {str(e)}"


def read_directory_context(dir_path: str, max_files: int = 50) -> str:
    """
    Recursively reads files from a directory and formats them as context.
    Skips common binary/cache directories and limits total files.
    """
    try:
        path = Path(dir_path)
        if not path.exists():
            print_error(f"Directory not found: {dir_path}")
            return ""

        if not path.is_dir():
            print_error(f"Not a directory: {dir_path}")
            return ""

        # Common patterns to exclude
        exclude_dirs = {
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            "dist",
            "build",
            ".cache",
            ".pytest_cache",
            "target",
        }
        exclude_exts = {
            ".pyc",
            ".pyo",
            ".so",
            ".dll",
            ".exe",
            ".bin",
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".pdf",
            ".zip",
            ".tar",
            ".gz",
        }

        # Find all files
        all_files = []
        for root, dirs, files in os.walk(path):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() not in exclude_exts:
                    all_files.append(file_path)

                if len(all_files) >= max_files:
                    break

            if len(all_files) >= max_files:
                break

        if not all_files:
            print_warning(f"No readable files found in {dir_path}")
            return ""

        # Read and format files
        context_parts = []
        files_read = 0

        for file_path in all_files[:max_files]:
            try:
                # Try to read as text
                content = file_path.read_text(encoding="utf-8", errors="ignore")

                # Skip if too large (>100KB)
                if len(content) > 100000:
                    console.print(
                        f"⏭️  Skipped (too large): {file_path.relative_to(path)}",
                        style=Colors.DIM,
                    )
                    continue

                rel_path = file_path.relative_to(path)
                context_parts.append(f"--- File: {rel_path} ---\n{content}\n")
                files_read += 1
                console.print(f"📄 Added: {rel_path}", style=Colors.DIM)

            except Exception:
                # Skip files that can't be read
                continue

        if files_read > 0:
            console.print(
                f"✅ Read {files_read} files from {dir_path}", style=Colors.GREEN
            )
            return "\n".join(context_parts)
        else:
            print_warning(f"No files could be read from {dir_path}")
            return ""

    except Exception as e:
        print_error(f"Error reading directory {dir_path}: {e}")
        return ""
