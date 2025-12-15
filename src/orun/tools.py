import os
import subprocess
import urllib.request
from html.parser import HTMLParser

# --- Helper for HTML Parsing ---


class SimpleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        clean = data.strip()
        if clean:
            self.text.append(clean)

    def get_text(self):
        return "\n".join(self.text)


# --- Actual Functions ---


def read_file(file_path: str) -> str:
    """Reads the content of a file."""
    try:
        if not os.path.exists(file_path):
            return f"Error: File '{file_path}' does not exist."
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


def write_file(file_path: str, content: str) -> str:
    """Writes content to a file (overwrites)."""
    try:
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to '{file_path}'"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def run_shell_command(command: str) -> str:
    """Executes a shell command."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        return output.strip()
    except Exception as e:
        return f"Error executing command: {str(e)}"


def list_directory(path: str = ".") -> str:
    """Lists files and directories in a given path."""
    try:
        if not os.path.exists(path):
            return f"Error: Path '{path}' does not exist."

        items = os.listdir(path)
        items.sort()

        output = []
        for item in items:
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                output.append(f"[DIR]  {item}")
            else:
                output.append(f"[FILE] {item}")

        return "\n".join(output) if output else "(empty directory)"
    except Exception as e:
        return f"Error listing directory: {str(e)}"


def search_files(path: str, pattern: str) -> str:
    """Searches for a text pattern in files within a directory (recursive)."""
    matches = []
    try:
        for root, _, files in os.walk(path):
            for file in files:
                # Skip common hidden/binary folders to save time
                if any(
                    x in root for x in [".git", "__pycache__", "node_modules", ".venv"]
                ):
                    continue

                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        for i, line in enumerate(lines):
                            if pattern in line:
                                matches.append(f"{file_path}:{i + 1}: {line.strip()}")
                                if len(matches) > 50:  # Limit results
                                    return (
                                        "\n".join(matches)
                                        + "\n... (too many matches, truncated)"
                                    )
                except Exception:
                    continue  # Skip files we can't read

        return "\n".join(matches) if matches else "No matches found."
    except Exception as e:
        return f"Error searching files: {str(e)}"


def fetch_url(url: str) -> str:
    """Fetches text content from a URL (stripped HTML)."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            html_content = response.read().decode("utf-8", errors="ignore")

        parser = SimpleHTMLParser()
        parser.feed(html_content)
        text = parser.get_text()

        # Limit size
        if len(text) > 10000:
            text = text[:10000] + "\n... (content truncated)"

        return text
    except Exception as e:
        return f"Error fetching URL: {str(e)}"


# --- Map for Execution ---

AVAILABLE_TOOLS = {
    "read_file": read_file,
    "write_file": write_file,
    "run_shell_command": run_shell_command,
    "list_directory": list_directory,
    "search_files": search_files,
    "fetch_url": fetch_url,
}

# --- Schemas for Ollama ---

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the specified path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path to the file to read",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Overwrites existing files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to write to the file",
                    },
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": "Execute a shell command (e.g., ls, git status, pytest).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to run",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories in a given directory path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": 'The directory path (default is current directory ".")',
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for a text pattern inside files in a directory (recursive).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The root directory to start searching from",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "The text string to search for",
                    },
                },
                "required": ["path", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch and read text content from a web URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to fetch"},
                },
                "required": ["url"],
            },
        },
    },
]
