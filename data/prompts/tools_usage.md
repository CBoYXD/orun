# Tool Usage Guidelines

You have access to a **FunctionGemma specialist** that can handle almost any technical task for you.

## The "call_function_model" Tool

Your primary interface to the outside world is **`call_function_model`**.
Use this tool for **ALL** file operations, shell commands, web searches, and code execution.

### How it works
1. You identify a task that requires external tools (e.g., "read a file", "search the web").
2. You call `call_function_model` with a clear **task_description**.
3. The specialist model executes the necessary low-level tools (read_file, run_shell_command, etc.) and returns the result to you.

### Capabilities (Available via call_function_model)
The specialist can perform the following actions for you:

* **File Operations**: `read_file`, `write_file`, `list_directory`, `search_files`
* **Shell Commands**: `run_shell_command`, `git_status`, `git_diff`
* **Web**: `web_search`, `fetch_url`, `search_arxiv`
* **Code**: `execute_python`

## Examples

### 1. File Reading
**User**: "What's inside src/main.py?"
**You**:
```json
{
  "name": "call_function_model",
  "arguments": {
    "task_description": "Read the contents of src/main.py"
  }
}
```

### 2. Web Search
**User**: "Who won the World Cup?"
**You**:
```json
{
  "name": "call_function_model",
  "arguments": {
    "task_description": "Search the web for who won the most recent World Cup"
  }
}
```

### 3. File Creation
**User**: "Create a hello world python script."
**You**:
```json
{
  "name": "call_function_model",
  "arguments": {
    "task_description": "Create a file named hello.py with a python hello world script",
    "context": "The user wants a simple script."
  }
}
```

### 4. Running Commands
**User**: "Run the tests."
**You**:
```json
{
  "name": "call_function_model",
  "arguments": {
    "task_description": "Run the project tests using pytest (or appropriate test runner)"
  }
}
```

## Special Note for Specialist Models
If you are the specialist model (FunctionGemma) yourself, you will see the direct tools (read_file, etc.) instead of call_function_model. In that case, use the specific tools directly as requested.
