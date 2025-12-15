import os
import subprocess

# --- Actual Functions ---

def read_file(file_path: str) -> str:
    """Reads the content of a file."""
    try:
        if not os.path.exists(file_path):
            return f"Error: File '{file_path}' does not exist."
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(file_path: str, content: str) -> str:
    """Writes content to a file (overwrites)."""
    try:
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to '{file_path}'"
    except Exception as e:
        return f"Error writing file: {str(e)}"

def run_shell_command(command: str) -> str:
    """Executes a shell command."""
    try:
        # Security note: shell=True is dangerous, but required for complex commands.
        # The core logic handles user confirmation.
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        return output.strip()
    except Exception as e:
        return f"Error executing command: {str(e)}"

# --- Map for Execution ---

AVAILABLE_TOOLS = {
    'read_file': read_file,
    'write_file': write_file,
    'run_shell_command': run_shell_command
}

# --- Schemas for Ollama ---

TOOL_DEFINITIONS = [
    {
        'type': 'function',
        'function': {
            'name': 'read_file',
            'description': 'Read the contents of a file at the specified path.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'file_path': {
                        'type': 'string',
                        'description': 'The path to the file to read',
                    },
                },
                'required': ['file_path'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'write_file',
            'description': 'Write content to a file. Overwrites existing files.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'file_path': {
                        'type': 'string',
                        'description': 'The path to the file to write',
                    },
                    'content': {
                        'type': 'string',
                        'description': 'The full content to write to the file',
                    },
                },
                'required': ['file_path', 'content'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'run_shell_command',
            'description': 'Execute a shell command (e.g., ls, git status, pytest).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'command': {
                        'type': 'string',
                        'description': 'The command to run',
                    },
                },
                'required': ['command'],
            },
        },
    },
]
