# orun-py

A Python CLI Agent wrapper for Ollama. It combines chat capabilities with autonomous tools (file I/O, shell execution, web fetching), built-in screenshot analysis, and 200+ prompt/strategy templates.

## Features

- **Autonomous Agent:** Can read/write files, run shell commands, search the web, and fetch URLs (with user confirmation).
- **Consensus Systems:** Multiple models working together in sequential pipelines or parallel aggregation.
- **Web Search:** Google Custom Search API (with DuckDuckGo fallback) for internet searches.
- **URL Fetching:** Jina AI Reader converts web pages to clean markdown optimized for LLM analysis.
- **arXiv Integration:** Search and retrieve academic papers directly from arXiv.
- **Screenshot Analysis:** Auto-detects and attaches recent screenshots from your Pictures folder.
- **Prompt Templates:** 200+ pre-defined templates for coding, analysis, writing, and more.
- **Strategy Templates:** Chain-of-Thought, Tree-of-Thought, and other reasoning strategies.
- **Conversation History:** SQLite-backed history lets you resume any session.
- **Model Management:** Sync models from Ollama and manage shortcuts.

## Installation

```bash
pip install orun-py
```

## Usage

### Agent & Query
Ask a question or give a task. The AI will use tools if necessary.
```bash
orun "Why is the sky blue?"
orun "Scan the current directory and list all Python files"
orun "Read src/main.py and explain how it works"
```

### Interactive Chat
Start a continuous session:
```bash
orun chat
```
Start chat with a specific model:
```bash
orun chat -m coder
```

### Prompt & Strategy Templates
Use a prompt template:
```bash
orun "Review this code" -p review_code
orun "Analyze this paper" -p analyze_paper
```

Use a reasoning strategy:
```bash
orun "Explain step by step" -s cot
orun "Explore multiple approaches" -s tot
```

Combine prompt and strategy:
```bash
orun "Debug this issue" -p analyze_incident -s cod
```

List available templates:
```bash
orun prompts      # List all prompt templates
orun strategies   # List all strategy templates
```

In chat mode, apply templates dynamically:
```bash
/prompt analyze_paper
/strategy cot
```

### Consensus Systems (Multi-Model)
Let multiple models collaborate for better results:

```bash
# List available consensus pipelines
orun consensus

# Code review: generate → review → refine
orun "Create a REST API for users" -C code_review

# Multi-expert: 3 models analyze, then synthesize
orun "Compare React vs Vue" -C multi_expert

# Vision + text: analyze image → refine response
orun "Explain this diagram" -i -C vision_consensus

# Vision + code: analyze UI → generate code
orun "Convert this mockup to React" -i -C vision_code
```

**7 Built-in Pipelines:**
1. **best_of_three** - Same model 3 times, show all results
2. **code_review** - Generate code → Review → Refine (3 models)
3. **iterative_improve** - Draft → Critique → Improve (3 models)
4. **multi_expert** - 3 models analyze, then synthesizer combines
5. **research_paper** - Research → Outline → Write (3 models)
6. **vision_consensus** - Vision analysis → Text refinement
7. **vision_code** - Vision analysis → Code generation

**Create Custom Pipelines:**
```bash
# Edit ~/.orun/config.json
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

User-defined pipelines automatically override defaults with the same name.

### Analyze Screenshots
Attach the most recent screenshot:
```bash
orun "What is this error?" -i
```
Attach the last 3 screenshots:
```bash
orun "Compare these images" -i 3x
```

### arXiv Integration
Search for academic papers and let the AI analyze them:
```bash
orun "Find recent papers about transformers in NLP"
orun "Get details about arXiv paper 1706.03762"
orun "Search for papers by Geoffrey Hinton and summarize his latest work"
```

In interactive chat, use the `/arxiv` command for direct access:
```bash
orun chat
> /arxiv quantum computing
> /arxiv 1706.03762
> /arxiv https://arxiv.org/abs/2301.07041
```

The AI can autonomously:
- Search arXiv by keywords, topics, or authors
- Retrieve full paper details (title, abstract, authors, PDF links)
- Analyze and summarize research papers
- Find relevant literature for your projects

The `/arxiv` command automatically detects whether you're searching or requesting a specific paper, fetches the data, and provides AI analysis without showing raw output.

### Web Search & URL Fetching
Search the web or fetch specific web pages in interactive chat:

**Web Search (DuckDuckGo with Language Detection):**
```bash
orun chat
> /search Python asyncio tutorials
> /search latest news about AI
```

**Fetch URL (via Jina AI Reader):**
```bash
orun chat
> /fetch https://example.com
> /fetch github.com/user/repo
```

Features:
- **Web Search**: DuckDuckGo with automatic language detection for region-appropriate results
- **Language Detection**: Automatically detects query language (Ukrainian, Russian, English, etc.) and sets appropriate region
- **URL Fetching**: Jina AI Reader converts pages to clean markdown optimized for LLM analysis
- **No Configuration Required**: Works out of the box with unlimited free searches
- **AI Analysis**: All results are analyzed and summarized by the AI

The AI can also autonomously call `web_search()` and `fetch_url()` tools during conversations.

### Model Management
Models are stored in `~/.orun/config.json` with support for multiple shortcuts per model and custom options.

Sync models from Ollama:
```bash
orun refresh
```

List available models with all their aliases:
```bash
orun models
```

Set default active model:
```bash
orun set-active llama3.1
```

Add shortcuts to models (multiple shortcuts per model supported):
```bash
orun shortcut llama3.1:8b llama
orun shortcut llama3.1:8b l3
# Now llama3.1:8b has shortcuts: ["llama3.1", "llama", "l3"]
```

**Model Configuration Structure**:
```json
{
  "models": {
    "llama3.1:8b": {
      "shortcuts": ["llama3.1", "llama", "l3"],
      "options": {"temperature": 0.7}
    }
  },
  "active_model": "llama3.1:8b"
}
```

### Conversation History
Conversation history is stored in `~/.orun/history.db` (SQLite database).

List recent conversations:
```bash
orun history
```

Continue a conversation by ID:
```bash
orun c 1
```

Continue the last conversation:
```bash
orun last
```

## Requirements
- Python 3.12+
- [Ollama](https://ollama.com/) running locally