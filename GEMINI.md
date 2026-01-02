# GEMINI.md

This file provides guidance to AI assistants when working with code in this repository.

## Project Overview

orun-py is a Python CLI wrapper for interacting with local LLMs via Ollama. It features:
- **Agent Capabilities**: Can read/write files, run shell commands, search files, and fetch URLs (with user confirmation).
- **Model Management**: JSON-based configuration (`~/.orun/config.json`) with multiple shortcuts per model and custom options.
- **Consensus Systems**: Multiple models working together (sequential pipelines or parallel aggregation).
- **Prompt Templates**: 200+ pre-defined templates for coding, analysis, writing, and more.
- **Strategy Templates**: Chain-of-Thought, Tree-of-Thought, and other reasoning strategies.
- **YOLO Mode**: Toggle confirmation-less execution mode for trusted commands.
- **Multimedia**: Built-in screenshot discovery and attachment.
- **History**: SQLite-based conversation tracking (`~/.orun/history.db`).

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

# Single-shot with Prompt/Strategy Templates
orun "Analyze this code" -p review_code         # Use prompt template
orun "Explain this" -s cot                      # Use strategy template
orun "Analyze this" -p analyze_paper -s tot    # Use both prompt and strategy

# Interactive Chat (Agent Mode)
orun                       # Start interactive session
orun -m coder              # Chat with specific model
orun -p create_coding_project                   # Start with prompt template
orun -s cot                                    # Start with strategy template

# Management
orun models                # List available models
orun refresh               # Sync models from Ollama
orun set-active <model>    # Set default active model
orun shortcut <m> <s>      # Create shortcut for model
orun history               # List recent conversations
orun prompts               # List available prompt templates
orun strategies            # List available strategy templates
orun consensus             # List available consensus pipelines
orun consensus-config      # Configure consensus pipelines

# Context
orun c <id>                # Continue conversation by ID
orun last                  # Continue last conversation

# Consensus (Multi-Model)
orun "prompt" -C <pipeline>  # Use consensus pipeline
orun "Write API" -C code_review              # Generate + review code
orun "Analyze topic" -C multi_expert         # Multiple models + synthesis
```

## Prompt and Strategy Templates

orun supports pre-defined prompt and strategy templates to streamline common tasks:

### Prompt Templates
Prompt templates are stored in `data/prompts/*.md` and provide ready-to-use prompts for specific tasks:
- **Code-related**: `review_code`, `create_coding_project`, `explain_code`
- **Analysis**: `analyze_paper`, `analyze_bill`, `analyze_claims`
- **Writing**: `write_essay`, `create_summary`, `improve_writing`
- **And 200+ more templates for various tasks**

### Strategy Templates
Strategy templates define reasoning approaches and are stored in `data/strategies/`:
- **cot**: Chain-of-Thought - Think step by step
- **tot**: Tree-of-Thoughts - Explore multiple reasoning paths
- **reflexion**: Reflect on and improve responses
- **cod**: Code-oriented decomposition
- **aot**: Algorithm-of-Thoughts
- **self-refine**: Iterative self-improvement
- **standard**: Standard direct response

### Using Templates in Chat Mode
In interactive chat, you can apply templates on-the-fly:
```bash
/prompt analyze_paper     # Apply a prompt template
/strategy cot            # Apply a strategy template
```

### Listing Available Templates
```bash
orun prompts              # List all prompt templates
orun strategies           # List all strategy templates
```

## Consensus Systems

Multiple models can work together to generate better responses:
- **Sequential**: Models run one after another (pipeline)
- **Parallel**: Models run independently, then results are synthesized

### Default Consensus Pipelines

7 built-in pipelines in `data/consensus/`:

1. **best_of_three** - Same model 3x, show all results
2. **code_review** - Generate → Review → Refine (3 models)
3. **iterative_improve** - Draft → Critique → Improve (3 models)
4. **multi_expert** - 3 models analyze, then synthesizer combines
5. **research_paper** - Research → Outline → Write (3 models)
6. **vision_consensus** - Vision analysis → Text refinement
7. **vision_code** - Vision analysis → Code generation

### Usage

```bash
# List pipelines
orun consensus

# Use consensus
orun "Create REST API" -C code_review
orun "Analyze topic" -C multi_expert
orun "Explain this" -i -C vision_consensus

# Create custom pipeline in ~/.orun/config.json
{
  "consensus": {
    "pipelines": {
      "my_workflow": {
        "type": "sequential",
        "models": [
          {"name": "model1", "role": "analyzer"},
          {"name": "model2", "role": "synthesizer"}
        ]
      }
    }
  }
}
```

**Note**: User-defined pipelines override defaults with the same name.

## Model Management

Models are stored in `~/.orun/config.json` with support for multiple shortcuts per model and custom options.

### Configuration Structure

```json
{
  "models": {
    "llama3.1:8b": {
      "shortcuts": ["llama3.1", "llama", "l3"],
      "options": {"temperature": 0.7}
    },
    "qwen3:30b": {
      "shortcuts": ["qwen3", "qwen"],
      "options": {}
    }
  },
  "active_model": "llama3.1:8b"
}
```

### Commands

- `orun refresh` - Sync models from Ollama (preserves existing shortcuts and options)
- `orun models` - List all models with all their aliases
- `orun set-active <model>` - Set default model (accepts full name or any shortcut)
- `orun shortcut <model> <alias>` - Add a new shortcut to a model

### Features

- **Multiple Shortcuts**: Each model can have multiple aliases
- **Per-Model Options**: Store custom options like temperature, top_p, etc.
- **Persistent Configuration**: Saved in `~/.orun/config.json`
- **Auto-Migration**: Old configs are automatically migrated to new format

### Examples

```bash
# Sync models from Ollama
orun refresh

# Add multiple shortcuts to one model
orun shortcut llama3.1:8b llama
orun shortcut llama3.1:8b l3

# Now you can use any of: llama3.1, llama, or l3
orun -m llama
orun "hello" -m l3
```

## Agent Tools
Tools are enabled by default for all chat/query modes. The AI can:
- `read_file`, `write_file`
- `list_directory`, `search_files`
- `run_shell_command`
- `fetch_url`, `web_search` - Fetch web pages and search the internet (DuckDuckGo with automatic language detection)
- `search_arxiv`, `get_arxiv_paper` - Search and retrieve academic papers from arXiv
User confirmation is required for execution.

## YOLO Mode (No Confirmations)

### What is YOLO Mode?
YOLO Mode allows the AI to execute shell commands without asking for confirmation, making interactions much faster. However, dangerous commands are still blocked for safety.

### How to Use YOLO Mode
1. **In Chat Mode** (always available):
   - Type `/yolo` to toggle YOLO mode on/off
   - Type `/reload` to reload configuration after editing the config file
   - Press `Ctrl+Y` as a hotkey to toggle YOLO mode
2. **For Single Commands**: Use the `--yolo` flag

Note: YOLO mode affects only tool-based commands (shell commands, file operations, etc.).

### Command Examples
```bash
# Start chat with YOLO mode pre-enabled
orun --yolo

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
