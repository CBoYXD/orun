# orun-py

A Python CLI wrapper for interacting with local LLMs via Ollama, featuring built-in support for analyzing screenshots and conversation history.

## Features

- **Quick AI Queries:** Send prompts to your local LLMs directly from the terminal.
- **Screenshot Analysis:** Automatically detect and attach the most recent screenshots from your user Pictures folder to your query.
- **Chat Mode:** Maintain a continuous conversation session.
- **Conversation History:** All conversations are saved locally and can be continued later.
- **Model Management:** Easily switch between different configured Ollama models using aliases.

## Installation

```bash
pip install orun-py
```

## Usage

### Basic Query
```bash
orun "Why is the sky blue?"
```

### Analyze Screenshots
By default, the `-i` flag grabs the most recent screenshot.
```bash
orun "What is this error?" -i
```
Analyze the last 3 screenshots:
```bash
orun "Compare these images" -i 3x
```
Select specific screenshots by index (1 is the newest):
```bash
orun "Look at the first and third image" -i 1 3
```

### Chat Mode
Start an interactive session:
```bash
orun --chat
```
Start chat with an initial prompt and image:
```bash
orun "Help me debug this" -i --chat
```

### Select Model
Use a specific model alias:
```bash
orun "Write python code" -m coder
```
List available models:
```bash
orun models
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
