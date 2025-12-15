# ORUN.md

This file provides guidance to AI assistants when working with code in this repository.

## Project Overview

orun-py is a Python CLI wrapper for interacting with local LLMs via Ollama. It features:
- **Agent Capabilities**: Can read/write files, run shell commands, search files, and fetch URLs (with user confirmation).
- **YOLO Mode**: Toggle confirmation-less execution mode for trusted commands.
- **Multimedia**: Built-in screenshot discovery and attachment.
- **History**: SQLite-based conversation tracking.

## Build and Development Commands

```bash
# Install dependencies (using uv)
uv sync

# Install package in development mode
uv pip install -e .

# Build distribution packages
uv build

# Publish to PyPI
uv publish

# Run the CLI directly
uv run orun "your prompt"
```

## Versioning and Release Workflow

1. **Test functionality** by running `orun` command.
2. **Update version** in `pyproject.toml`.
3. **Build**: `uv build`
4. **Publish**: `uv publish`

## Project Structure

```
src/orun/
├── main.py        # Entry point and argument parsing
├── core.py        # AI logic (chat loops, Ollama interaction)
├── commands.py    # CLI command handlers
├── tools.py       # Agent tools (read_file, run_shell_command, etc.)
├── utils.py       # Helpers (colors, config, screenshot finding)
└── db.py          # Database module (Peewee ORM)
```

## CLI Commands

```bash
# Query (Single-shot Agent)
orun "prompt"              # Execute prompt with active model
orun "prompt" -m coder     # Use specific model
orun "prompt" -i           # Attach most recent screenshot
orun "prompt" -i 3x        # Attach last 3 screenshots

# Interactive Chat (Agent Mode)
orun chat                  # Start interactive session
orun chat -m coder         # Chat with specific model

# Management
orun models                # List available models
orun refresh               # Sync models from Ollama
orun set-active <model>    # Set default active model
orun shortcut <m> <s>      # Create shortcut for model
orun history               # List recent conversations

# Context
orun c <id>                # Continue conversation by ID
orun last                  # Continue last conversation
```

## Agent Tools
Tools are enabled by default for all chat/query modes. The AI can:
- `read_file`, `write_file`
- `list_directory`, `search_files`
- `run_shell_command`
- `fetch_url`
User confirmation is required for execution.

## YOLO Mode (No Confirmations)

### What is YOLO Mode?
YOLO Mode allows the AI to execute shell commands without asking for confirmation, making interactions much faster. However, dangerous commands are still blocked for safety.

### How to Use YOLO Mode
1. **In Chat Mode** (always available):
   - Type `/yolo` to toggle YOLO mode on/off
   - Type `/reload-yolo` to reload configuration after editing the config file
   - Press `Ctrl+Y` as a hotkey to toggle YOLO mode
2. **For Single Commands**: Use the `--yolo` flag

Note: YOLO mode affects only tool-based commands (shell commands, file operations, etc.).

### Command Examples
```bash
# Start chat with YOLO mode pre-enabled
orun chat --yolo

# Execute a single command without confirmation
orun "run git status" --yolo

# Continue a conversation with YOLO mode
orun c 42 "make build" --yolo
```

### Safety Features
- **Forbidden Commands**: Dangerous commands like `rm -rf /`, `dd if=`, etc. are always blocked
- **Pattern Detection**: Regex patterns catch potentially dangerous variants
- **Whitelist Support**: Safe commands (ls, git status, etc.) are pre-configured

### Configuration
The orun configuration is stored in `~/.orun/config.json` (same directory as the database):
- `yolo.forbidden_commands`: Commands that are always blocked
- `yolo.whitelisted_commands`: Commands considered safe

The configuration file is automatically created with sensible defaults the first time you run orun. You can edit this file to customize which commands require confirmation in YOLO mode.

The JSON structure allows for future configuration options under different sections.