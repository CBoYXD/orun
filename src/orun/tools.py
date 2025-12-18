import html
import os
import subprocess
import urllib.request
from html.parser import HTMLParser

import arxiv
from ddgs import DDGS
from langdetect import detect, LangDetectException


# --- Helper for HTML Parsing ---


class StructuredHTMLParser(HTMLParser):
    """Convert HTML into a lightly formatted text/markdown output."""

    HEADING_PREFIX = {
        "h1": "# ",
        "h2": "## ",
        "h3": "### ",
        "h4": "#### ",
        "h5": "##### ",
        "h6": "###### ",
    }

    BLOCK_TAGS = {
        "p",
        "div",
        "section",
        "article",
        "header",
        "footer",
        "main",
        "aside",
    }

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.list_stack: list[dict] = []
        self.skip_depth = 0
        self.capture_title = False
        self.title_buffer: list[str] = []
        self.title: str | None = None
        self.in_pre = False
        self.in_code = False
        self.link_href: str | None = None
        self.link_text: list[str] = []

    def _append(self, text: str, ensure_space: bool = False) -> None:
        if not text:
            return
        if ensure_space and self.parts:
            if not self.parts[-1].endswith((" ", "\n")) and not text.startswith(
                (" ", "\n")
            ):
                self.parts.append(" ")
        self.parts.append(text)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attr_map = dict(attrs)

        if tag in ("script", "style"):
            self.skip_depth += 1
            return

        if tag == "title":
            self.capture_title = True
            self.title_buffer = []
            return

        if self.skip_depth:
            return

        if tag in self.HEADING_PREFIX:
            self._append("\n\n" + self.HEADING_PREFIX[tag])
        elif tag in self.BLOCK_TAGS:
            self._append("\n\n")
        elif tag == "br":
            self._append("\n")
        elif tag == "blockquote":
            self._append("\n\n> ")
        elif tag == "ul":
            self.list_stack.append({"type": "ul", "index": 0})
            self._append("\n")
        elif tag == "ol":
            self.list_stack.append({"type": "ol", "index": 0})
            self._append("\n")
        elif tag == "li":
            indent = "  " * max(len(self.list_stack) - 1, 0)
            bullet = "- "
            if self.list_stack:
                current = self.list_stack[-1]
                if current["type"] == "ol":
                    current["index"] += 1
                    bullet = f"{current['index']}. "
            self._append("\n" + indent + bullet)
        elif tag == "a":
            self.link_href = attr_map.get("href", "").strip()
            self.link_text = []
        elif tag == "pre":
            self.in_pre = True
            self._append("\n```\n")
        elif tag == "code":
            if not self.in_pre:
                self.in_code = True
                self._append("`")
        elif tag in ("strong", "b"):
            self._append("**")
        elif tag in ("em", "i"):
            self._append("_")
        elif tag == "table":
            self._append("\n\n[Table]\n")
        elif tag == "tr":
            self._append("\n")
        elif tag in ("th", "td"):
            self._append(" | ")

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in ("script", "style"):
            if self.skip_depth:
                self.skip_depth -= 1
            return

        if tag == "title":
            self.capture_title = False
            title = "".join(self.title_buffer).strip()
            if title:
                self.title = title
            return

        if self.skip_depth:
            return

        if tag == "a":
            text = " ".join(self.link_text).strip()
            href = (self.link_href or "").strip()
            if href.startswith("//"):
                href = f"https:{href}"
            if text:
                if href:
                    self._append(f"[{text}]({href})", ensure_space=True)
                else:
                    self._append(text, ensure_space=True)
            elif href:
                self._append(href, ensure_space=True)
            self.link_href = None
            self.link_text = []
        elif tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            self._append("\n")
        elif tag == "pre":
            if self.in_pre:
                self._append("\n```\n")
            self.in_pre = False
        elif tag == "code":
            if not self.in_pre and self.in_code:
                self._append("`")
                self.in_code = False
        elif tag in ("strong", "b"):
            self._append("**")
        elif tag in ("em", "i"):
            self._append("_")
        elif tag == "blockquote":
            self._append("\n")

    def handle_data(self, data):
        if self.capture_title:
            self.title_buffer.append(data)
            return

        if self.skip_depth:
            return

        text = data if self.in_pre else " ".join(html.unescape(data).split())
        if not text:
            return

        if self.link_href is not None:
            self.link_text.append(text)
        else:
            self._append(text, ensure_space=True)

    def get_text(self) -> str:
        raw = "".join(self.parts)
        lines = raw.splitlines()
        cleaned = []
        blank_count = 0
        for line in lines:
            if line.strip():
                cleaned.append(line.rstrip())
                blank_count = 0
            else:
                blank_count += 1
                if blank_count < 2:
                    cleaned.append("")
        return "\n".join(cleaned).strip()


# --- Actual Functions ---


def read_file(file_path: str) -> str:
    """Reads the content of a file."""
    try:
        if not os.path.exists(file_path):
            return f"Error: File '{file_path}' does not exist."
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


def write_file(file_path: str, content: str) -> str:
    """Writes content to a file (overwrites)."""
    try:
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to '{file_path}'"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def run_shell_command(command: str) -> str:
    """Executes a shell command."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        return output.strip()
    except Exception as e:
        return f"Error executing command: {str(e)}"


def list_directory(path: str = ".") -> str:
    """Lists files and directories in a given path."""
    try:
        if not os.path.exists(path):
            return f"Error: Path '{path}' does not exist."

        items = os.listdir(path)
        items.sort()

        output = []
        for item in items:
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                output.append(f"[DIR]  {item}")
            else:
                output.append(f"[FILE] {item}")

        return "\n".join(output) if output else "(empty directory)"
    except Exception as e:
        return f"Error listing directory: {str(e)}"


def search_files(path: str, pattern: str) -> str:
    """Searches for a text pattern in files within a directory (recursive)."""
    matches = []
    try:
        for root, _, files in os.walk(path):
            for file in files:
                # Skip common hidden/binary folders to save time
                if any(
                    x in root for x in [".git", "__pycache__", "node_modules", ".venv"]
                ):
                    continue

                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        for i, line in enumerate(lines):
                            if pattern in line:
                                matches.append(f"{file_path}:{i + 1}: {line.strip()}")
                                if len(matches) > 50:  # Limit results
                                    return (
                                        "\n".join(matches)
                                        + "\n... (too many matches, truncated)"
                                    )
                except Exception:
                    continue  # Skip files we can't read

        return "\n".join(matches) if matches else "No matches found."
    except Exception as e:
        return f"Error searching files: {str(e)}"


def fetch_url(url: str) -> str:
    """
    Fetches and converts URL content to readable text.
    Uses Jina AI Reader API (LLM-optimized, free) with fallback to custom parser.
    """
    normalized = url.strip()
    if not normalized:
        return "Error: URL is empty."
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"

    # Try Jina AI Reader first (optimized for LLM, returns clean markdown)
    try:
        jina_url = f"https://r.jina.ai/{normalized}"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; orun/1.0)",
            "X-Return-Format": "markdown"  # Ensure markdown format
        }
        req = urllib.request.Request(jina_url, headers=headers)

        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode("utf-8", errors="ignore")

            # Jina returns clean markdown - just validate and return
            if content and len(content) > 50:  # Basic validation
                if len(content) > 15000:
                    content = content[:15000] + "\n... (content truncated)"

                return f"{content}\n\nSource: {normalized} (via Jina AI Reader)".strip()
    except Exception as e:
        # Jina failed, fall back to custom parser
        pass

    # Fallback: Custom HTML parser
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        req = urllib.request.Request(normalized, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            html_content = response.read().decode(charset, errors="ignore")
    except Exception as e:
        return f"Error fetching URL: {str(e)}"

    parser = StructuredHTMLParser()
    parser.feed(html_content)
    text = parser.get_text()

    if not text:
        text = "No readable text content found."

    if len(text) > 15000:
        text = text[:15000] + "\n... (content truncated)"

    if parser.title:
        header = f"{parser.title}\n{'=' * len(parser.title)}\n\n"
    else:
        header = ""

    return f"{header}{text}\n\nSource: {normalized}".strip()


def search_arxiv(query: str, max_results: int = 5) -> str:
    """Search for papers on arXiv by query string."""
    if arxiv is None:
        return "Error: arxiv library is not installed. Run 'uv sync' to install dependencies."

    try:
        max_results = min(int(max_results), 20)  # Limit to max 20 results
    except (ValueError, TypeError):
        max_results = 5

    try:
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )

        results = []
        for i, paper in enumerate(search.results(), 1):
            authors = ", ".join([author.name for author in paper.authors[:3]])
            if len(paper.authors) > 3:
                authors += " et al."

            result = f"{i}. **{paper.title}**\n"
            result += f"   Authors: {authors}\n"
            result += f"   Published: {paper.published.strftime('%Y-%m-%d')}\n"
            result += f"   arXiv ID: {paper.entry_id.split('/')[-1]}\n"
            result += f"   PDF: {paper.pdf_url}\n"
            # Truncate abstract if too long
            abstract = paper.summary.replace("\n", " ").strip()
            if len(abstract) > 300:
                abstract = abstract[:300] + "..."
            result += f"   Abstract: {abstract}\n"

            results.append(result)

        if not results:
            return f"No papers found for query: {query}"

        header = f"Found {len(results)} paper(s) for '{query}':\n\n"
        return header + "\n".join(results)

    except Exception as e:
        return f"Error searching arXiv: {str(e)}"


def get_arxiv_paper(arxiv_id: str) -> str:
    """Get detailed information about a specific arXiv paper by its ID."""
    if arxiv is None:
        return "Error: arxiv library is not installed. Run 'uv sync' to install dependencies."

    try:
        # Clean up the arxiv_id (remove version number if present)
        arxiv_id = arxiv_id.strip().replace("https://arxiv.org/abs/", "").replace("http://arxiv.org/abs/", "")
        if "v" in arxiv_id:
            arxiv_id = arxiv_id.split("v")[0]

        search = arxiv.Search(id_list=[arxiv_id])
        paper = next(search.results())

        # Format authors
        authors = ", ".join([author.name for author in paper.authors])

        # Format categories
        categories = ", ".join(paper.categories)

        # Build detailed output
        output = f"**{paper.title}**\n\n"
        output += f"Authors: {authors}\n\n"
        output += f"Published: {paper.published.strftime('%Y-%m-%d')}\n"
        if paper.updated != paper.published:
            output += f"Updated: {paper.updated.strftime('%Y-%m-%d')}\n"
        output += f"\nCategories: {categories}\n"
        output += f"arXiv ID: {paper.entry_id.split('/')[-1]}\n"
        output += f"PDF: {paper.pdf_url}\n"

        if paper.doi:
            output += f"DOI: {paper.doi}\n"

        if paper.journal_ref:
            output += f"Journal Reference: {paper.journal_ref}\n"

        if paper.comment:
            output += f"\nComment: {paper.comment}\n"

        output += f"\n**Abstract:**\n{paper.summary}\n"

        if paper.primary_category:
            output += f"\nPrimary Category: {paper.primary_category}\n"

        return output.strip()

    except StopIteration:
        return f"Error: Paper with arXiv ID '{arxiv_id}' not found."
    except Exception as e:
        return f"Error fetching arXiv paper: {str(e)}"


def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo with automatic language detection.
    Detects query language and returns region-appropriate results.
    """
    try:
        max_results = min(int(max_results), 10)  # Limit to max 10 results
    except (ValueError, TypeError):
        max_results = 5

    # Detect language based on query text
    def detect_language(text: str) -> str:
        """Detect language and return appropriate DuckDuckGo region code."""
        # Language code to DuckDuckGo region mapping
        LANG_TO_REGION = {
            'uk': 'ua-uk',  # Ukrainian
            'ru': 'ru-ru',  # Russian
            'en': 'us-en',  # English
            'de': 'de-de',  # German
            'fr': 'fr-fr',  # French
            'es': 'es-es',  # Spanish
            'it': 'it-it',  # Italian
            'pt': 'pt-br',  # Portuguese
            'pl': 'pl-pl',  # Polish
            'nl': 'nl-nl',  # Dutch
            'ja': 'jp-jp',  # Japanese
            'ko': 'kr-kr',  # Korean
            'zh-cn': 'cn-zh',  # Chinese Simplified
            'zh-tw': 'tw-tzh',  # Chinese Traditional
        }

        try:
            lang = detect(text)
            return LANG_TO_REGION.get(lang, 'us-en')  # Default to US English
        except (LangDetectException, Exception):
            # If detection fails, default to US English
            return 'us-en'

    # Search with DuckDuckGo
    try:
        region = detect_language(query)
        ddgs = DDGS()
        results = list(ddgs.text(query, region=region, max_results=max_results))

        if not results:
            return f"No results found for query: {query}"

        output = [f"**Web Search Results for '{query}':**\n"]
        for i, result in enumerate(results, 1):
            title = result.get("title", "No title")
            link = result.get("href", result.get("link", ""))
            snippet = result.get("body", result.get("snippet", "No description"))

            output.append(f"{i}. **{title}**")
            output.append(f"   URL: {link}")
            output.append(f"   {snippet}\n")

        return "\n".join(output)

    except Exception as e:
        return f"Error performing web search: {str(e)}"


# --- Map for Execution ---

AVAILABLE_TOOLS = {
    "read_file": read_file,
    "write_file": write_file,
    "run_shell_command": run_shell_command,
    "list_directory": list_directory,
    "search_files": search_files,
    "fetch_url": fetch_url,
    "search_arxiv": search_arxiv,
    "get_arxiv_paper": get_arxiv_paper,
    "web_search": web_search,
}

# --- Schemas for Ollama ---

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the specified path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path to the file to read",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Overwrites existing files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to write to the file",
                    },
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": "Execute a shell command (e.g., ls, git status, pytest).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to run",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories in a given directory path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": 'The directory path (default is current directory ".")',
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for a text pattern inside files in a directory (recursive).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The root directory to start searching from",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "The text string to search for",
                    },
                },
                "required": ["path", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch and read text content from a web URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to fetch"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_arxiv",
            "description": "Search for academic papers on arXiv by query. Returns title, authors, abstract, and PDF link.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'quantum computing', 'neural networks', or author name)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5, max: 20)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_arxiv_paper",
            "description": "Get detailed information about a specific arXiv paper by its ID (e.g., '2301.07041').",
            "parameters": {
                "type": "object",
                "properties": {
                    "arxiv_id": {
                        "type": "string",
                        "description": "The arXiv ID of the paper (e.g., '2301.07041' or full URL)",
                    },
                },
                "required": ["arxiv_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using Google Custom Search API (with DuckDuckGo fallback). Returns titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g., 'Python programming tutorials', 'latest news AI')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5, max: 10)",
                    },
                },
                "required": ["query"],
            },
        },
    },
]
