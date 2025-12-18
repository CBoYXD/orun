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

# Single-shot with Prompt/Strategy Templates
orun "Analyze this code" -p review_code         # Use prompt template
orun "Explain this" -s cot                      # Use strategy template
orun "Analyze this" -p analyze_paper -s tot    # Use both prompt and strategy

# Interactive Chat (Agent Mode)
orun chat                  # Start interactive session
orun chat -m coder         # Chat with specific model
orun chat -p create_coding_project              # Start with prompt template
orun chat -s cot                                   # Start with strategy template

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
orun config-search         # View Google Search API configuration
orun config-search <key> <cse_id>  # Set Google Search API credentials

# Context
orun c <id>                # Continue conversation by ID
orun last                  # Continue last conversation
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

orun supports "consensus" mode where multiple models work together to generate better responses. This allows:
- **Sequential pipelines**: Models run one after another, each building on previous outputs
- **Parallel aggregation**: Multiple models analyze the same prompt, then results are synthesized

### Available Consensus Pipelines

Default pipelines are provided in `data/consensus/`:

1. **code_review** (sequential)
   - Step 1: Code generator creates clean, efficient code
   - Step 2: Reviewer analyzes for bugs and improvements
   - Use case: Generate and review code in one command

2. **multi_expert** (parallel)
   - Multiple models analyze the same question independently
   - Synthesizer combines insights from all responses
   - Use case: Get diverse perspectives on complex questions

3. **research_paper** (sequential)
   - Step 1: Researcher gathers information (can use web_search)
   - Step 2: Outliner creates detailed paper structure
   - Step 3: Writer composes comprehensive paper
   - Use case: Research and write papers automatically

4. **iterative_improve** (sequential)
   - Step 1: Drafter creates initial response
   - Step 2: Critic identifies weaknesses
   - Step 3: Improver creates final version
   - Use case: Iterative refinement for quality

5. **best_of_three** (parallel)
   - Same model runs 3 times with high temperature
   - Shows all responses for comparison
   - Use case: Generate multiple creative options

### Using Consensus

```bash
# List available pipelines
orun consensus

# Configure pipelines
orun consensus-config

# Use in single-shot mode
orun "Write a REST API for user management" --consensus code_review
orun "Analyze microservices pros/cons" -C multi_expert

# With options
orun "Research quantum computing" -C research_paper --yolo
orun "Create a story" -C best_of_three -o story.txt
```

### In Chat Mode

```bash
orun chat
> /consensus              # List available pipelines
> /consensus code_review  # Info about using consensus (not yet implemented in TUI)
```

Note: Full consensus integration in interactive chat mode is planned for a future release. Currently, use single-shot mode (`orun "prompt" -C pipeline`) for consensus features.

### Creating Custom Consensus Pipelines

Add custom pipelines in `~/.orun/config.json`:

```json
{
  "consensus": {
    "pipelines": {
      "my_pipeline": {
        "description": "Custom workflow",
        "type": "sequential",
        "models": [
          {
            "name": "qwen2.5-coder:latest",
            "role": "analyzer",
            "system_prompt": "Analyze the code and identify issues",
            "options": {"temperature": 0.3}
          },
          {
            "name": "llama3.2:latest",
            "role": "fixer",
            "system_prompt": "Fix the identified issues",
            "options": {"temperature": 0.5}
          }
        ],
        "pass_strategy": "accumulate"
      }
    }
  }
}
```

### Configuration Options

**Sequential pipelines:**
- `type`: "sequential"
- `models`: Array of model configurations
  - `name`: Full model name (e.g., "llama3.2:latest")
  - `role`: Descriptive name for this step (optional)
  - `system_prompt`: Instructions for this model (optional)
  - `options`: Model parameters like temperature, top_p
- `pass_strategy`: How context is passed between models
  - `accumulate`: Pass all previous messages (default)
  - `last_only`: Only pass last model's output
  - `synthesis`: Synthesize all previous outputs

**Parallel pipelines:**
- `type`: "parallel"
- `models`: Array of model configurations (simpler, usually just name and options)
- `aggregation`: How to combine results
  - `method`: "synthesis" or "best_of"
  - `synthesizer_model`: Model to use for synthesis (if method is "synthesis")
  - `synthesis_prompt`: Custom prompt for synthesis (optional)

### Tools in Consensus

All models in a consensus pipeline have access to agent tools (read_file, run_shell_command, etc.) if tools are enabled. This allows models to:
- Sequential: Each step can use tools, and results are passed to next model
- Parallel: Each model can use tools independently

YOLO mode works the same way in consensus as in normal mode.

## Agent Tools
Tools are enabled by default for all chat/query modes. The AI can:
- `read_file`, `write_file`
- `list_directory`, `search_files`
- `run_shell_command`
- `fetch_url`, `web_search` - Fetch web pages and search the internet
- `search_arxiv`, `get_arxiv_paper` - Search and retrieve academic papers from arXiv
User confirmation is required for execution.

### arXiv Integration
The AI can search and retrieve academic papers from arXiv using two methods:

#### 1. Agent Tools (Automatic)
**search_arxiv(query, max_results=5)**
- Search for papers by keywords, topics, or author names
- Returns title, authors, publication date, abstract preview, and PDF link
- Max results: 20 papers per search
- Example: `"Find papers about transformer architectures"`

**get_arxiv_paper(arxiv_id)**
- Get detailed information about a specific paper by its arXiv ID
- Returns full abstract, all authors, categories, DOI, journal reference
- Accepts arXiv ID (e.g., "1706.03762") or full URL
- Example: `"Get details for paper 1706.03762"`

#### 2. TUI Command (Interactive Chat)
In interactive chat mode, use the `/arxiv` command:

```bash
# Search for papers by query
/arxiv transformer neural networks

# Get specific paper by ID
/arxiv 1706.03762

# Get paper by URL
/arxiv https://arxiv.org/abs/2301.07041
```

The `/arxiv` command automatically:
- Detects if input is a search query or paper ID
- Fetches paper information from arXiv
- Sends data to AI for analysis (without showing raw output)
- AI provides a comprehensive summary with insights

These tools allow the AI to:
- Research recent publications in any field
- Summarize and analyze academic papers
- Find relevant literature for your projects
- Stay updated with the latest research

### Web Search Integration
The AI can search the web and fetch web pages using two methods:

#### 1. Agent Tool (Automatic)
**web_search(query, max_results=5)**
- Search the web using Google Custom Search API (with DuckDuckGo fallback)
- Returns titles, URLs, and snippets from search results
- Max results: 10 per search
- Automatically falls back to DuckDuckGo if Google API is not configured or quota exceeded
- Example: `"Search the web for Python asyncio tutorials"`

**fetch_url(url)**
- Fetch and parse content from a specific URL
- Uses Jina AI Reader API (LLM-optimized, free) for clean markdown conversion
- Falls back to custom HTML parser if Jina is unavailable
- Returns page title and formatted content optimized for LLM analysis
- Example: `"Fetch https://example.com"`

#### 2. TUI Commands (Interactive Chat)
In interactive chat mode, use these commands:

**Web Search:**
```bash
# Search the web (Google/DuckDuckGo)
/search Python programming tutorials
/search latest AI news
```

**Fetch URL:**
```bash
# Fetch and parse a specific web page
/fetch https://example.com
/fetch github.com/user/repo
```

These commands automatically:
- **`/search`**: Searches the web using Google API (with DuckDuckGo fallback)
- **`/fetch`**: Fetches page content via Jina AI Reader (LLM-optimized)
- Send results to AI for analysis
- AI provides a comprehensive summary with key insights

#### Configuration
Web search uses Google Custom Search API by default, with DuckDuckGo as fallback.

To configure Google Custom Search API (optional but recommended for better results):
1. Get an API key from [Google Cloud Console](https://console.cloud.google.com/)
2. Create a Custom Search Engine at [Google CSE](https://programmablesearchengine.google.com/)
3. Configure using the CLI command:

```bash
# Set Google API credentials
orun config-search YOUR_API_KEY YOUR_CSE_ID

# View current configuration
orun config-search
```

Alternatively, you can manually edit `~/.orun/config.json`:
```json
{
  "search": {
    "google_api_key": "YOUR_API_KEY_HERE",
    "google_cse_id": "YOUR_CSE_ID_HERE"
  }
}
```

**Free Tier Limits:**
- Google Custom Search: 100 queries/day (free)
- DuckDuckGo: Unlimited (no API key required)

If Google API is not configured or quota is exceeded, the system automatically falls back to DuckDuckGo.

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