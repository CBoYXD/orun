# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

orun-py is a Python CLI wrapper for interacting with local LLMs via Ollama, featuring built-in screenshot analysis support.

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

# Run with Python module
python -m orun.main "your prompt"
```

## Versioning and Release Workflow

When making changes to the package:

1. **Test functionality** by running `orun` command to verify changes work correctly
2. **Update version** in `pyproject.toml` - increment by `0.0.1` (e.g., `1.0.1` -> `1.0.2`)
   - When version reaches `X.Y.9`, next version becomes `X.(Y+1).0` (e.g., `1.0.9` -> `1.1.0`)
3. **Build**: `uv build`
4. **Publish**: `uv publish`
5. **Commit** with message format:
   ```
   Update to {version}. Changes: {description of changes}
   ```

## Project Structure

```
src/orun/
├── __init__.py    # Package init (empty)
└── main.py        # All CLI logic - entry point, argument parsing, Ollama integration
```

The entire application lives in `main.py` with no separate modules. Key components:
- **MODELS dict**: Model aliases mapping (e.g., "coder" -> "qwen3-coder:30b")
- **SCREENSHOT_DIRS**: Default paths for screenshot discovery
- **main()**: Entry point registered as `orun` command via pyproject.toml

## Key Dependencies

- **ollama**: Python client for Ollama API (local LLM server)
- **hatchling**: Build backend for package distribution

## CLI Usage Patterns

```bash
orun "prompt"              # Basic query with default model
orun "prompt" -m coder     # Use model alias
orun "prompt" -i           # Attach most recent screenshot
orun "prompt" -i 3x        # Attach last 3 screenshots
orun "prompt" -i 1 3       # Attach screenshots by index
orun --chat                # Interactive chat mode
orun --list-models         # Show available model aliases
```
