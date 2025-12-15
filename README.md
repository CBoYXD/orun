# orun-py

A Python CLI Agent wrapper for Ollama. It combines chat capabilities with autonomous tools (file I/O, shell execution, web fetching) and built-in screenshot analysis.

## Features

- **Autonomous Agent:** Can read/write files, run shell commands, and fetch URLs (with user confirmation).
- **Screenshot Analysis:** Auto-detects and attaches recent screenshots from your Pictures folder.
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

### Analyze Screenshots
Attach the most recent screenshot:
```bash
orun "What is this error?" -i
```
Attach the last 3 screenshots:
```bash
orun "Compare these images" -i 3x
```

### Model Management
Sync models from Ollama:
```bash
orun refresh
```
List available models:
```bash
orun models
```
Set default active model:
```bash
orun set-active llama3.1
```
Create a shortcut:
```bash
orun shortcut llama3.1:8b l3
```

### Conversation History
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