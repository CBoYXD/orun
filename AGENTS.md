# AGENTS.md

This file provides comprehensive guidance and reference for AI assistants (Antigravity, Claude, Gemini, GPT, etc.) working on the `orun-py` codebase.

---

## 1. Project Overview

**orun-py** is a feature-rich Python CLI and TUI agent wrapper for interacting with local LLMs via [Ollama](https://ollama.com/). It transforms local models into capable AI agents equipped with tools, multi-model consensus workflows, customizable prompt/strategy templates, and safe command execution.

### Key Capabilities
- **Autonomous Agent**: Executes tools (file I/O, shell execution, web search, URL fetching, arXiv search, git operations, Python execution) with confirmation or in YOLO mode.
- **Interactive TUI**: Built with [Textual](https://textual.textualize.io/) for rich terminal chat, markdown rendering, tool inspection, and interactive slash commands.
- **Model Management**: JSON configuration (`~/.orun/config.json`) supporting multiple shortcuts/aliases per model and per-model options (temperature, top_p, etc.).
- **Consensus Systems**: Multi-model collaboration via sequential pipelines (e.g. Drafter → Critic → Refiner) and parallel aggregation (multiple models + synthesis).
- **Prompt & Strategy Templates**: 200+ built-in prompt templates and reasoning strategies (CoT, ToT, Reflexion, CoD, AoT, Self-Refine) with user override support (`~/.orun/data/`).
- **System Profile**: Automatic language detection and matching (UA, RU, EN, etc.) + smart/minimalist tool usage guidelines.
- **YOLO Mode**: Confirmation-free tool execution protected by safety whitelists and regex pattern detection for forbidden dangerous commands.
- **Multimedia Support**: Auto-detects and attaches recent screenshots (`-i`, `-i 3x`).
- **Conversation History**: SQLite-backed persistent history (`~/.orun/history.db`) via Peewee ORM with session continuation (`orun c <id>`, `orun last`).
- **Robyn MCP Server**: Optional lightweight HTTP/MCP server (`orun mcp-server`) powered by Robyn with dynamic plugin support (`~/.orun/mcps`).

---

## 2. Development & Environment Setup

The project uses [uv](https://docs.astral.sh/uv/) for package and dependency management.

### Setup & Installation
```bash
# Sync dependencies and create virtual environment with all extras (dev, mcp)
uv sync --all-extras

# Install package in editable mode
uv pip install -e ".[dev,mcp]"

# Run the CLI directly
uv run orun --help
uv run orun "your prompt"
```

### Testing & Code Coverage
The test suite uses `pytest` with `pytest-cov`:
```bash
# Run all tests with coverage report
uv run pytest

# Run tests without coverage if needed
uv run pytest --no-cov

# Run specific test file
uv run pytest tests/test_core.py
```

### Building & Publishing
```bash
# Build wheel and sdist
uv build

# Publish to PyPI (requires PyPI credentials / token)
uv publish
```

---

## 3. Versioning & Release Workflow

`orun-py` adheres to [PEP 440](https://peps.python.org/pep-0440/) versioning with support for pre-releases (`alpha`, `beta`, `rc`) and post-releases (`post`).

### Automated Releases (`just`)
The release workflow is defined in `justfile` and scripts in `scripts/`:
```bash
# Format: just publish <part> <type> "<message>"
# part: patch | minor | major | current
# type: stable | alpha | beta | rc | post

# Standard releases
just publish patch stable "Fix issue with tool parsing"     # 1.2.3 -> 1.2.4
just publish minor stable "Add new consensus pipelines"     # 1.2.3 -> 1.3.0
just publish major stable "Breaking architecture update"    # 1.2.3 -> 2.0.0

# Pre-releases
just publish patch alpha "Initial alpha testing"            # 1.2.3 -> 1.2.4a1
just publish current alpha "Fix alpha bugs"                 # 1.2.4a1 -> 1.2.4a2
just publish current beta "Promote to beta"                 # 1.2.4a2 -> 1.2.4b1
just publish current rc "Release candidate"                 # 1.2.4b1 -> 1.2.4rc1
just publish current stable "Final release"                 # 1.2.4rc1 -> 1.2.4

# Post-releases (hotfixes)
just publish current post "Critical hotfix"                 # 1.2.4 -> 1.2.4.post1
```

### Manual Release Steps
```bash
# 1. Bump version
python scripts/version_manager.py patch stable

# 2. Sync and build
uv sync
uv build

# 3. Publish
uv publish

# 4. Commit and push
git add .
python scripts/git_commit_release.py "Release commit message"
git push
```

---

## 4. Codebase Architecture

```
orun/
├── data/                       # Built-in package data
│   ├── consensus/              # Default consensus pipelines (json)
│   ├── profiles/               # Profile definitions (e.g. system.json)
│   ├── prompts/                # 200+ prompt templates (md)
│   └── strategies/             # Reasoning strategy templates (json/md)
├── scripts/                    # Release and version management scripts
│   ├── git_commit_release.py
│   └── version_manager.py
├── src/orun/                   # Application source code
│   ├── __init__.py             # Package init
│   ├── cache.py                # Response caching utilities
│   ├── commands.py             # CLI command handlers and subcommands
│   ├── config.py               # Config loading & defaults (~/.orun/config.json)
│   ├── consensus.py            # Multi-model consensus execution (sequential & parallel)
│   ├── consensus_config.py     # Consensus pipeline management & CLI interactive config
│   ├── core.py                 # Core AI agent loop, Ollama API integration, single-shot
│   ├── db.py                   # Peewee ORM models & SQLite operations (~/.orun/history.db)
│   ├── http_client.py          # Unified HTTP client helpers
│   ├── main.py                 # CLI entry point, argument parsing, routing
│   ├── mcp_plugins.py          # User MCP plugin loader (~/.orun/mcps/)
│   ├── mcp_server.py           # Robyn-based HTTP/MCP server endpoints (/health, /chat)
│   ├── models_config.py        # Model shortcuts, active model resolution, options
│   ├── profiles_manager.py     # Profile loader & merger
│   ├── prompts_manager.py      # Prompt and strategy template resolver
│   ├── rich_utils.py           # Rich console formatting, colors, panels, banners
│   ├── search_config.py        # Search configuration and API settings
│   ├── tools.py                # 14 Agent tools definitions, execution, validation
│   ├── tui.py                  # Textual interactive terminal chat application
│   ├── utils.py                # Screenshot finder, clipboard, token estimation, system info
│   └── yolo.py                 # YOLO mode rules, whitelist check, forbidden patterns
├── tests/                      # Pytest test suite & conftest fixtures
├── pyproject.toml              # Build config, dependencies, entry points
└── justfile                    # Just task runner recipes
```

---

## 5. Agent Tools Reference

All tools are implemented in `src/orun/tools.py` and are enabled by default for both single-shot and interactive chat modes.

| Tool | Description |
|---|---|
| `read_file(path, start_line, end_line)` | Read file contents (with optional line range slice). |
| `write_file(path, content, overwrite)` | Create or overwrite files. |
| `list_directory(path, recursive, max_depth)` | List directory structure and file sizes. |
| `search_files(path, pattern, content_search)` | Find files by name pattern or search text inside files. |
| `run_shell_command(command, timeout)` | Execute bash/shell command with timeout and output capture. |
| `fetch_url(url)` | Fetch web page and parse markdown via Jina Reader (with HTML fallback). |
| `web_search(query, max_results)` | Search DuckDuckGo with automatic language and region detection. |
| `search_arxiv(query, max_results)` | Search academic papers on arXiv (title, authors, abstract, PDF). |
| `get_arxiv_paper(arxiv_id)` | Retrieve detailed metadata and abstract for a specific arXiv ID. |
| `git_status()` | Run `git status --short` and return current git repository state. |
| `git_diff(staged)` | Inspect unstaged or staged git diff. |
| `git_log(max_count)` | View commit history log. |
| `git_commit(message, add_all)` | Stage files and make a git commit. |
| `execute_python(code)` | Run Python code snippet in an isolated subprocess. |

### Smart Tool Usage & System Profile
The core system profile (`data/profiles/system.json`):
1. **Language Matching**: Automatically detects user's language and replies in the exact same language (Russian, Ukrainian, English, etc.).
2. **Minimalist Tool Use**: Models are instructed to think first, calculate directly if possible, and invoke tools only when strictly required (e.g. reading actual files or running real commands).

---

## 6. CLI Usage & Slash Commands

### CLI Invocations
```bash
# Interactive TUI mode
orun
orun -m qwen2.5-coder:32b
orun --yolo

# Single-shot execution
orun "Explain how asyncio event loops work"
orun "Refactor src/orun/main.py" -m coder --yolo
orun "Review this PR diff" -p review_code
orun "Design a distributed cache" -s tot

# Screenshot attachment
orun "What error is shown in this screenshot?" -i
orun "Compare these mockups" -i 3x

# Consensus pipelines
orun "Build a JWT authentication service" -C code_review
orun "Evaluate monolithic vs microservices" -C multi_expert

# Conversation continuation
orun c 42 "Now add unit tests for that function"
orun last "Make it faster"

# Model & Template management
orun models
orun refresh
orun set-active llama3.3:70b
orun shortcut qwen2.5-coder:32b coder
orun prompts
orun strategies
orun consensus
orun consensus-config
```

### Interactive TUI Slash Commands
Within `orun` interactive chat:
- `/help` — Show available slash commands.
- `/model <alias>` — Switch active model on the fly.
- `/prompt <template>` — Apply prompt template to current query.
- `/strategy <template>` — Apply reasoning strategy (CoT, ToT, Reflexion, etc.).
- `/profile <name>` — Load a combined system profile.
- `/consensus <pipeline>` — View consensus pipelines.
- `/arxiv <query|id|url>` — Search arXiv or summarize a specific paper.
- `/search <query>` — Perform web search.
- `/fetch <url>` — Fetch and summarize URL content.
- `/yolo` (or `Ctrl+Y`) — Toggle YOLO mode on/off.
- `/reload` — Reload configuration and profiles from disk.
- `/clear` — Clear current chat session messages.
- `/history` — Browse recent conversations.
- `/export <file>` — Export conversation to markdown.

---

## 7. Consensus Systems (Multi-Model)

Consensus allows multiple local models to collaborate on a single task.

### Built-in Pipelines (`data/consensus/`)
1. **`best_of_three`** *(Parallel)*: Runs same model 3 times with high temperature to choose or compare the best variation.
2. **`code_review`** *(Sequential)*: Generator → Reviewer → Refiner.
3. **`iterative_improve`** *(Sequential)*: Drafter → Critic → Improver.
4. **`multi_expert`** *(Parallel)*: Multiple distinct models evaluate independently, then a synthesizer unifies the findings.
5. **`research_paper`** *(Sequential)*: Researcher (with web search) → Outliner → Final Writer.
6. **`vision_consensus`** *(Sequential)*: Vision model analyzes image → text model refines output.
7. **`vision_code`** *(Sequential)*: Vision model inspects UI mockup → coder model generates code.

### Custom Pipelines
Custom pipelines can be placed in `~/.orun/data/consensus/<name>.json` and will automatically override defaults with the same name.

---

## 8. YOLO Mode & Safety Features

YOLO Mode executes tool actions (such as running shell commands or writing files) without pausing for interactive terminal confirmation.

### Safety Layers
1. **Forbidden Commands**: Dangerous commands (e.g. `rm -rf /`, `dd if=`, `:(){ :|:& };:`, raw disk writes) are strictly blocked by regex patterns in `src/orun/yolo.py`.
2. **Safe Whitelist**: Safe read-only commands (e.g. `ls`, `git status`, `pwd`, `cat`, `echo`) execute immediately.
3. **User Configuration**: Whitelists and blacklists can be customized in `~/.orun/config.json` under the `"yolo"` key.

---

## 9. Optional Robyn MCP Server

`orun` includes an optional Robyn-based server (`src/orun/mcp_server.py`) that exposes `orun` over HTTP and supports Robyn MCP plugins:
```bash
# Start server
orun mcp-server --host 127.0.0.1 --port 8000 -m llama3.3
```

- `GET /health` → `{"status": "ok"}`
- `POST /chat` → `{"response": "..."}`
- Plugins located in `~/.orun/mcps/*.py` are dynamically loaded at startup.

---

## 10. Guidelines for AI Agents Working on This Repository

1. **Test Before Committing**: Always run `uv run pytest` to ensure all tests pass and coverage remains intact.
2. **Preserve Tool Compatibility**: Ensure changes to `src/orun/tools.py` maintain schema compatibility with Ollama tool call definitions.
3. **Maintain User Data Separation**: Default configs/prompts live in `data/`, but user overrides in `~/.orun/` must always take priority.
4. **Keep Async & TUI Non-blocking**: In `src/orun/tui.py`, heavy I/O operations and model streaming must remain async/worker-threaded.
