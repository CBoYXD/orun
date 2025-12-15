# ORUN.md

This file provides guidance to AI assistants when working with code in this repository.

## Project Overview

orun-py is a Python CLI wrapper for interacting with local LLMs via Ollama. It features:
- **Agent Capabilities**: Can read/write files, run shell commands, search files, and fetch URLs (with user confirmation).
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