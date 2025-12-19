# ORUN.md

This file provides guidance to AI assistants when working with code in this repository.

## Project Overview

orun-py is a Python CLI wrapper for interacting with local LLMs via Ollama. It features:
- **Agent Capabilities**: Can read/write files, run shell commands, search files, and fetch URLs (with user confirmation).
- **Model Management**: JSON-based configuration with multiple shortcuts per model and custom options.
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

orun-py uses [PEP 440](https://peps.python.org/pep-0440/) versioning with support for pre-releases and post-releases.

### Version Types

- **Standard releases**: `1.2.3`
- **Alpha**: `1.2.3a1`, `1.2.3a2` (early testing)
- **Beta**: `1.2.3b1`, `1.2.3b2` (feature complete, needs testing)
- **Release Candidate**: `1.2.3rc1`, `1.2.3rc2` (final testing)
- **Post releases**: `1.2.3.post1` (hotfixes)

### Release Commands (using just)

The universal command format is: `just publish <part> <type> "message"`
- **part**: `patch`, `minor`, `major`, or `current` (keeps same version numbers)
- **type**: `stable`, `alpha`, `beta`, `rc`, or `post`

```bash
# ============================================================
# STANDARD RELEASES (stable versions)
# ============================================================
just publish patch stable "Fix bug X"         # 1.2.3 -> 1.2.4
just publish minor stable "Add feature Y"     # 1.2.3 -> 1.3.0
just publish major stable "Breaking change"   # 1.2.3 -> 2.0.0

# ============================================================
# PRE-RELEASES: Create first alpha/beta/rc
# ============================================================
# These bump the patch version and add pre-release suffix
just publish patch alpha "Start alpha testing"    # 1.2.3 -> 1.2.4a1
just publish patch beta "Start beta testing"      # 1.2.3 -> 1.2.4b1
just publish patch rc "Start release candidate"   # 1.2.3 -> 1.2.4rc1

# Can also bump minor/major with pre-release:
just publish minor alpha "New feature alpha"      # 1.2.3 -> 1.3.0a1
just publish major beta "Breaking change beta"    # 1.2.3 -> 2.0.0b1

# ============================================================
# PRE-RELEASES: Bump pre-release number (a1→a2, b1→b2, rc1→rc2)
# ============================================================
# Use 'current' to keep version numbers and only increment pre-release number
just publish current alpha "Fix alpha bugs"       # 1.2.4a1 -> 1.2.4a2
just publish current alpha "More alpha fixes"     # 1.2.4a2 -> 1.2.4a3

just publish current beta "Fix beta bugs"         # 1.2.4b1 -> 1.2.4b2
just publish current beta "Beta improvements"     # 1.2.4b2 -> 1.2.4b3

just publish current rc "Fix RC bugs"             # 1.2.4rc1 -> 1.2.4rc2
just publish current rc "Final RC fixes"          # 1.2.4rc2 -> 1.2.4rc3

# ============================================================
# POST RELEASES: Hotfixes for already published stable versions
# ============================================================
just publish current post "Hotfix for critical bug"   # 1.2.4 -> 1.2.4.post1
just publish current post "Another hotfix"            # 1.2.4.post1 -> 1.2.4.post2

# ============================================================
# FINALIZE: Remove pre-release suffix and publish stable
# ============================================================
just publish current stable "Final release"       # 1.2.4a3 -> 1.2.4
just publish current stable "RC approved"         # 1.2.4rc3 -> 1.2.4

# ============================================================
# EXAMPLES: Complete workflow scenarios
# ============================================================

# Scenario 1: Standard patch release
just publish patch stable "Fix authentication bug"    # 1.2.3 -> 1.2.4

# Scenario 2: Alpha → Beta → RC → Stable
just publish patch alpha "Start testing new API"      # 1.2.3 -> 1.2.4a1
just publish current alpha "Fix API bugs"             # 1.2.4a1 -> 1.2.4a2
just publish current beta "Move to beta"              # 1.2.4a2 -> 1.2.4b1
just publish current beta "Beta fixes"                # 1.2.4b1 -> 1.2.4b2
just publish current rc "Release candidate"           # 1.2.4b2 -> 1.2.4rc1
just publish current rc "Final fixes"                 # 1.2.4rc1 -> 1.2.4rc2
just publish current stable "Stable release"          # 1.2.4rc2 -> 1.2.4

# Scenario 3: Hotfix after stable release
just publish current post "Security hotfix"           # 1.2.4 -> 1.2.4.post1
just publish current post "Another urgent fix"        # 1.2.4.post1 -> 1.2.4.post2
```

### Manual Release Workflow

If not using `just`:

```bash
# 1. Update version
python scripts/version_manager.py patch   # or alpha, beta, rc, post, etc.

# 2. Sync dependencies
uv sync

# 3. Build
uv build

# 4. Publish
uv publish

# 5. Commit and push
git add .
python scripts/git_commit_release.py "Your changes"
git push
```

### Version Bumping Logic

The version manager intelligently handles bumping based on current version state:

**Standard Version Bumps (patch/minor/major):**
- **Patch**: `1.2.3` → `1.2.4` (increments patch number)
- **Minor**: `1.2.3` → `1.3.0` (increments minor, resets patch)
- **Major**: `1.2.3` → `2.0.0` (increments major, resets minor and patch)

**Pre-release Logic (alpha/beta/rc):**
- If current version is **NOT** in that pre-release phase: Bumps patch and adds pre-release suffix
  - `1.2.3` + `alpha` → `1.2.4a1`
  - `1.2.3a2` + `beta` → `1.2.4b1` (switches to beta)
- If current version **IS** in that pre-release phase: Only increments pre-release number
  - `1.2.4a1` + `alpha` → `1.2.4a2` (bump alpha number)
  - `1.2.4b1` + `beta` → `1.2.4b2` (bump beta number)
  - `1.2.4rc1` + `rc` → `1.2.4rc2` (bump rc number)

**Post-release Logic:**
- If current version has **NO** post suffix: Adds `.post1`
  - `1.2.4` + `post` → `1.2.4.post1`
- If current version **HAS** post suffix: Increments post number
  - `1.2.4.post1` + `post` → `1.2.4.post2`

**Finalize (stable):**
- Removes pre-release suffix without changing version numbers
  - `1.2.4a1` + `stable` → `1.2.4`
  - `1.2.4rc3` + `stable` → `1.2.4`

**Using 'current' part:**
- `current` keeps the base version numbers unchanged, only modifies pre-release/post suffixes
- Useful for incrementing pre-release numbers or switching between pre-release types
  - `just publish current alpha "msg"` on `1.2.4a1` → `1.2.4a2`
  - `just publish current beta "msg"` on `1.2.4a2` → `1.2.4b1`

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

# Context
orun c <id>                # Continue conversation by ID
orun last                  # Continue last conversation
```

## System Profile (Automatic Language Matching)

orun **automatically matches the AI's response language to your input language**. This feature is enabled by default through the `system` profile.

### How It Works

- Write in **Ukrainian** → AI responds in Ukrainian
- Write in **English** → AI responds in English
- Write in **Russian** → AI responds in Russian
- Write in **any language** → AI responds in that language

The AI will maintain the same language throughout the entire response, including explanations, code comments, error messages, and examples.

### Implementation

The system profile is implemented through:
1. **Prompt Template**: `data/prompts/language_matching.md` - Contains language matching instructions
2. **System Profile**: `data/profiles/system.json` - Automatically loaded for all queries

### Customization

**To disable language matching:**
Create a custom `system` profile in `~/.orun/data/profiles/system.json`:
```json
{
  "description": "Custom system profile (language matching disabled)",
  "included_prompts": []
}
```

**To modify language matching behavior:**
Create a custom prompt in `~/.orun/data/prompts/language_matching.md`:
```markdown
Your custom language matching instructions here
```

**To extend the system profile:**
Add additional prompts to your custom system profile:
```json
{
  "description": "Extended system profile",
  "included_prompts": ["language_matching", "my_custom_prompt"]
}
```

User-defined profiles and prompts in `~/.orun/data/` automatically override default ones.

### Technical Details

- The `system` profile is **always loaded first** for all queries (chat mode and single-shot)
- User-specified profiles (via `--profile`) are merged after the system profile
- This ensures consistent language behavior and core AI settings across all interactions
- The system profile has special status in `orun profiles` output (highlighted in yellow)

## Prompt and Strategy Templates

orun supports pre-defined prompt and strategy templates to streamline common tasks. Templates are automatically loaded from both packaged defaults and user-custom locations.

### Prompt Templates
**Default prompts** are included with the package and provide ready-to-use prompts for specific tasks:
- **Code-related**: `review_code`, `create_coding_project`, `explain_code`
- **Analysis**: `analyze_paper`, `analyze_bill`, `analyze_claims`
- **Writing**: `write_essay`, `create_summary`, `improve_writing`
- **And 200+ more templates for various tasks**

**Custom prompts** can be added to `~/.orun/data/prompts/` as `.md` files. Each file should contain the prompt text. The filename (without `.md`) becomes the prompt name.

Example: Create `~/.orun/data/prompts/my_prompt.md`:
```markdown
You are an expert reviewer. Analyze the following and provide detailed feedback on:
1. Strengths
2. Weaknesses
3. Recommendations
```

### Strategy Templates
**Default strategies** define reasoning approaches:
- **cot**: Chain-of-Thought - Think step by step
- **tot**: Tree-of-Thoughts - Explore multiple reasoning paths
- **reflexion**: Reflect on and improve responses
- **cod**: Code-oriented decomposition
- **aot**: Algorithm-of-Thoughts
- **self-refine**: Iterative self-improvement
- **standard**: Standard direct response

**Custom strategies** can be added to `~/.orun/data/strategies/` as `.json` or `.md` files.

Example: Create `~/.orun/data/strategies/my_strategy.json`:
```json
{
  "prompt": "Think deeply about this problem. First, identify the core issue. Then, brainstorm solutions. Finally, evaluate each solution."
}
```

### Using Templates in Chat Mode
In interactive chat, you can apply templates on-the-fly:
```bash
/prompt analyze_paper     # Apply a prompt template (default or custom)
/strategy cot            # Apply a strategy template (default or custom)
```

### Listing Available Templates
```bash
orun prompts              # List all prompt templates (default + custom)
orun strategies           # List all strategy templates (default + custom)
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

Custom consensus pipelines are stored as individual JSON files in `~/.orun/data/consensus/`. Each file represents one pipeline.

**Creating a custom pipeline:**

1. Create a JSON file in `~/.orun/data/consensus/` with the pipeline name (e.g., `my_pipeline.json`)
2. Add the pipeline configuration following the structure below
3. The pipeline will be automatically loaded next time you run orun

**Example: `~/.orun/data/consensus/my_pipeline.json`**

```json
{
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
```

### Overriding Default Pipelines

You can override any default pipeline by creating a file with the same name in `~/.orun/data/consensus/`. For example, to customize the `code_review` pipeline, create `~/.orun/data/consensus/code_review.json`:

```json
{
  "description": "My custom code review workflow",
  "type": "sequential",
  "models": [
    {"name": "my-model:latest", "role": "coder"},
    {"name": "another-model:latest", "role": "reviewer"}
  ],
  "pass_strategy": "accumulate"
}
```

Your custom `code_review.json` will be used instead of the default one. The `orun consensus` command shows which pipelines are user-defined vs default.

**Note:** Legacy config.json format is still supported for backward compatibility, but using separate JSON files in `~/.orun/data/consensus/` is recommended.

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

**Sync models from Ollama:**
```bash
orun refresh
```
This scans Ollama for available models and adds them to config.json. Existing shortcuts and options are preserved.

**List all models:**
```bash
orun models
```
Shows all models with all their aliases.

**Set active model:**
```bash
orun set-active llama3.1
```
Sets the default model to use. Accepts either full name or any shortcut.

**Add shortcuts:**
```bash
orun shortcut llama3.1:8b llama
orun shortcut llama3.1:8b l3
```
Models can have multiple shortcuts. All shortcuts can be used interchangeably with `-m` flag or in chat commands.

### Features

- **Multiple Shortcuts**: Each model can have multiple aliases (e.g., `llama3.1`, `llama`, `l3`)
- **Per-Model Options**: Store custom options like temperature, top_p, etc. (reserved for future use)
- **Persistent Configuration**: All settings saved in `~/.orun/config.json`
- **Backward Compatible**: Old alias-based configs are automatically migrated

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
- Search the web using DuckDuckGo with automatic language detection
- Automatically selects appropriate region based on query language (Ukrainian, Russian, English, etc.)
- Returns titles, URLs, and snippets from search results
- Max results: 10 per search
- No configuration required, unlimited free searches
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
- **`/search`**: Searches the web using DuckDuckGo with automatic language detection
- **`/fetch`**: Fetches page content via Jina AI Reader (LLM-optimized)
- Send results to AI for analysis
- AI provides a comprehensive summary with key insights

#### Features
- **Automatic Language Detection**: Search queries are analyzed to detect the language (Ukrainian, Russian, English, etc.)
- **Region-Appropriate Results**: DuckDuckGo region parameter is automatically set based on detected language
- **No Configuration Required**: Works out of the box with unlimited free searches
- **Multiple Languages Supported**: Ukrainian (ua-uk), Russian (ru-ru), English (us-en), German (de-de), French (fr-fr), Spanish (es-es), Italian (it-it), Portuguese (pt-br), Polish (pl-pl), Dutch (nl-nl), Japanese (jp-jp), Korean (kr-kr), Chinese (cn-zh, tw-tzh)

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