import html
import ipaddress
import json
import os
import re
import shlex
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from typing import Any, Mapping
from html.parser import HTMLParser

import arxiv
DDGS = object  # type: ignore[misc, assignment]
try:
    from ddgs import DDGS as _DDGS
except Exception:  # pragma: no cover - optional dependency fallback
    pass
else:
    DDGS = _DDGS
from langdetect import LangDetectException, detect
from orun import config as orun_config, utils
from orun.http_client import (
    HttpClient,
    HttpClientError,
    HttpClientSettings,
)
from orun.cache import get_cached_text, set_cached_text
from orun.rich_utils import print_error, print_warning
from orun.search_config import search_config

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
# Ensure DDGS is always present for consumers that patch it during tests.
if "DDGS" not in globals():
    DDGS = object  # type: ignore[misc, assignment]

def __getattr__(name: str):
    if name == "DDGS":
        return globals().get("DDGS", object)
    raise AttributeError(f"module {__name__} has no attribute {name}")

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

_HTTP_CLIENT: HttpClient | None = None
_HTTP_CLIENT_SETTINGS: HttpClientSettings | None = None


def _get_http_client(timeout: float, retries: int, backoff: float) -> HttpClient:
    """
    Lazily initialize and reuse an HTTP client with consistent settings.
    """
    global _HTTP_CLIENT, _HTTP_CLIENT_SETTINGS
    settings = HttpClientSettings(
        timeout=timeout,
        retries=retries,
        backoff_factor=backoff,
        user_agent="Mozilla/5.0 (compatible; orun/1.0)",
    )
    if _HTTP_CLIENT is None or _HTTP_CLIENT_SETTINGS != settings:
        _HTTP_CLIENT = HttpClient(settings=settings)
        _HTTP_CLIENT_SETTINGS = settings
    return _HTTP_CLIENT


def _result_envelope(
    success: bool,
    source: Mapping[str, Any],
    data: Any | None = None,
    error: str | None = None,
    message: str | None = None,
) -> str:
    """
    Produce a standardized result envelope for tool outputs.
    """
    payload: dict[str, Any] = {"success": success, "source": dict(source)}
    if message:
        payload["message"] = message
    if error:
        payload["error"] = error
    if data is not None:
        payload["data"] = data
    return json.dumps(payload, ensure_ascii=False, indent=2)
def _resolve_host_ips(host: str) -> list[IPAddress]:
    """
    Resolve a hostname to a list of IP addresses.

    Args:
        host: Hostname or IP literal to resolve.

    Returns:
        List of resolved IP addresses.

    Raises:
        ValueError: If the host cannot be resolved.
    """
    try:
        ip_addr = ipaddress.ip_address(host)
        return [ip_addr]
    except ValueError:
        try:
            addr_info = socket.getaddrinfo(host, None)
        except Exception as exc:  # socket.gaierror and similar
            raise ValueError(f"Could not resolve hostname '{host}': {exc}") from exc

        addresses: list[IPAddress] = []
        for info in addr_info:
            try:
                resolved_ip = ipaddress.ip_address(info[4][0])
            except Exception:
                continue
            if resolved_ip not in addresses:
                addresses.append(resolved_ip)
        if not addresses:
            raise ValueError(f"No valid IP addresses found for hostname '{host}'.")
        return addresses


def _is_private_ip(ip: IPAddress) -> bool:
    """
    Determine whether an IP address is private or otherwise unsafe for fetching.

    Args:
        ip: IP address to inspect.

    Returns:
        True if the address is private, loopback, link-local, multicast,
        reserved, or unspecified.
    """
    return any(
        [
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        ]
    )


def _validate_fetch_destination(
    host: str, limits: dict, port: str | None = None
) -> tuple[bool, str | None]:
    """
    Validate whether a URL destination is allowed to be fetched.

    Args:
        host: Hostname from the URL.
        limits: Limits configuration section.
        port: Optional port extracted from the URL for logging context.

    Returns:
        Tuple of (allowed, error_message). error_message is None when allowed is True.
    """
    allow_hosts = {h.lower() for h in limits.get("fetch_allow_hosts", []) if h}
    block_hosts = {h.lower() for h in limits.get("fetch_block_hosts", []) if h}
    block_private_networks = limits.get("fetch_block_private_networks", True)

    host_key = host.lower()
    if allow_hosts and host_key not in allow_hosts:
        return (
            False,
            f"Host '{host}'{f':{port}' if port else ''} is not in the configured fetch allowlist.",
        )

    if host_key in block_hosts:
        return (
            False,
            f"Host '{host}'{f':{port}' if port else ''} is blocked by configuration.",
        )

    try:
        resolved_ips = _resolve_host_ips(host)
    except ValueError as exc:
        return False, str(exc)

    for ip_addr in resolved_ips:
        ip_key = str(ip_addr).lower()
        if ip_key in block_hosts:
            return (
                False,
                f"IP '{ip_addr}'{f':{port}' if port else ''} is blocked by configuration.",
            )
        if block_private_networks and _is_private_ip(ip_addr):
            return (
                False,
                f"Access to host '{host}' is blocked because it resolves to a private or local network address ({ip_addr}).",
            )

    return True, None


def read_file(file_path: str) -> str:
    """Reads the content of a file."""
    try:
        allowed, reason = utils.is_path_allowed(file_path)
        if not allowed:
            return f"Error: {reason}"
        if not os.path.exists(file_path):
            return f"Error: File '{file_path}' does not exist."
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            limits = orun_config.get_section("limits")
            max_chars = limits.get("file_read_max_chars", 200000)
            if max_chars and len(content) > max_chars:
                content = content[:max_chars] + "\n... (truncated)"
            return content
    except Exception as e:
        return f"Error reading file: {str(e)}"


def write_file(file_path: str, content: str) -> str:
    """Writes content to a file (overwrites)."""
    try:
        allowed, reason = utils.is_path_allowed(file_path)
        if not allowed:
            return f"Error: {reason}"
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to '{file_path}'"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def _is_filesystem_command(command: str) -> bool:
    """
    Heuristic to determine if a shell command touches the filesystem.

    The check is intentionally conservative: redirections and common
    filesystem-oriented commands trigger sandbox validation.
    """
    tokens = shlex.split(command)
    if not tokens:
        return False

    fs_keywords = {
        "cd",
        "ls",
        "pwd",
        "cat",
        "head",
        "tail",
        "cp",
        "mv",
        "rm",
        "touch",
        "mkdir",
        "rmdir",
        "find",
        "grep",
        "sed",
        "awk",
        "chmod",
        "chown",
    }

    if tokens[0] in fs_keywords:
        return True

    redirection_patterns = [r">", r">>", r"2>", r"\|"]
    return any(re.search(pattern, command) for pattern in redirection_patterns)


def _is_command_allowed(command: str) -> tuple[bool, str]:
    """Check allowlist/denylist rules for shell commands."""
    shell_config = orun_config.get_section("shell")
    allowlist = shell_config.get("allowlist") or []
    denylist = shell_config.get("denylist") or []

    for blocked in denylist:
        if blocked and blocked.lower() in command.lower():
            return False, f"Command blocked by denylist entry: '{blocked}'"

    if allowlist:
        for allowed in allowlist:
            if allowed and allowed.lower() in command.lower():
                break
        else:
            return False, "Command not in allowlist"

    return True, ""


def is_shell_command_allowed(command: str) -> tuple[bool, str]:
    """
    Public wrapper for allowlist/denylist checks.

    Returns:
        Tuple of (is_allowed, reason). The reason is empty when allowed.
    """
    return _is_command_allowed(command)


def _validate_filesystem_access(command: str) -> tuple[bool, str]:
    """
    Validate commands that interact with the filesystem using sandbox rules.

    We inspect common path arguments (including redirections and cwd changes) and
    reuse the sandbox allowlist to prevent accidental traversal outside the
    configured roots.
    """
    try:
        parsed = shlex.split(command)
    except ValueError:
        return False, "Invalid command syntax"

    paths_to_check: set[str] = set()
    tokens_to_skip = {"&&", "||", "|"}

    if parsed:
        # Handle explicit cwd changes (cd /path && ...)
        if parsed[0] == "cd" and len(parsed) > 1:
            paths_to_check.add(parsed[1])

    redirection_match = re.findall(r">\s*([^\s]+)|>>\s*([^\s]+)|2>\s*([^\s]+)", command)
    for match in redirection_match:
        for target in match:
            if target:
                paths_to_check.add(target)

    # Capture positional path arguments for common filesystem commands
    fs_command_args = {"cat", "head", "tail", "cp", "mv", "rm", "touch", "mkdir", "rmdir"}
    if parsed and parsed[0] in fs_command_args:
        for token in parsed[1:]:
            if token.startswith("-") or token in tokens_to_skip:
                continue
            paths_to_check.add(token)

    for path in paths_to_check:
        allowed, reason = utils.is_path_allowed(path)
        if not allowed:
            return False, reason

    return True, ""


def run_shell_command(command: str) -> str:
    """Executes a shell command with allow/deny checks and sandbox enforcement."""
    allowed, reason = is_shell_command_allowed(command)
    if not allowed:
        return f"Error executing command: {reason}"

    if _is_filesystem_command(command):
        allowed, reason = _validate_filesystem_access(command)
        if not allowed:
            return f"Error executing command: {reason}"

    try:
        limits = orun_config.get_section("limits")
        timeout = limits.get("shell_timeout_seconds", 20)
        max_chars = limits.get("shell_output_limit", 12000)
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        output = output.strip()
        if max_chars and len(output) > max_chars:
            output = output[:max_chars] + "\n... (truncated)"
        return output
    except subprocess.TimeoutExpired:
        return "Error executing command: timed out"
    except Exception as e:
        return f"Error executing command: {str(e)}"


def list_directory(path: str = ".") -> str:
    """Lists files and directories in a given path."""
    try:
        allowed, reason = utils.is_path_allowed(path)
        if not allowed:
            return f"Error: {reason}"
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
        allowed, reason = utils.is_path_allowed(path)
        if not allowed:
            return f"Error: {reason}"
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


def fetch_url(url: str, http_client: HttpClient | None = None) -> str:
    """
    Fetch and normalize URL content with retries and caching.
    """
    normalized = url.strip()
    if not normalized:
        return _result_envelope(
            success=False,
            source={"tool": "fetch_url"},
            error="Error: URL is empty.",
        )

    def _validation_error(message: str) -> str:
        return f"Error: {message}"

    def _ip_block_reason(
        address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    ) -> str | None:
        """Return the reason an IP address should be blocked, if any."""

        if address.is_loopback or address.is_unspecified:
            return "loopback or unspecified address"
        if address.is_private:
            return "private network"
        if address.is_reserved:
            return "reserved network"
        if address.is_multicast:
            return "multicast address"
        if address.is_link_local:
            return "link-local address"
        return None

    def _blocked_hostname_reason(hostname: str) -> str | None:
        """Determine if the hostname targets a restricted network."""

        lowered = hostname.lower()
        if lowered in {"localhost", "ip6-localhost"} or lowered.endswith(
            ".localhost"
        ):
            return "localhost hostnames are not allowed"

        try:
            ip_addr = ipaddress.ip_address(hostname)
            ip_reason = _ip_block_reason(ip_addr)
            if ip_reason:
                return f"host resolves to a {ip_reason}: {hostname}"
        except ValueError:
            pass

        try:
            infos = socket.getaddrinfo(hostname, None)
        except Exception:
            return None

        for info in infos:
            try:
                candidate_ip = ipaddress.ip_address(info[4][0])
            except ValueError:
                continue
            ip_reason = _ip_block_reason(candidate_ip)
            if ip_reason:
                return f"host resolves to a {ip_reason}: {candidate_ip}"

        return None

    parsed = urllib.parse.urlparse(normalized)
    if not parsed.scheme:
        normalized = f"https://{normalized}"
        parsed = urllib.parse.urlparse(normalized)

    if parsed.scheme not in {"http", "https"}:
        return _validation_error("Unsupported URL scheme. Only http and https are allowed.")

    if not parsed.hostname:
        return _validation_error("URL must include a hostname.")

    blocked_reason = _blocked_hostname_reason(parsed.hostname)
    if blocked_reason:
        return _validation_error(
            f"Access to host '{parsed.hostname}' is blocked ({blocked_reason})."
        )

    limits = orun_config.get_section("limits")
    timeout = limits.get("fetch_timeout_seconds", 20)
    max_chars = limits.get("fetch_max_chars", 15000)
    max_bytes = max_chars if max_chars else None
    retries = limits.get("fetch_retry_count", 1)
    backoff = limits.get("fetch_backoff_seconds", 1.0)

    def _truncate(text: str) -> str:
        if max_chars and len(text) > max_chars:
            return text[:max_chars] + "\n... (content truncated)"
        return text

    allowed, validation_error = _validate_fetch_destination(
        parsed.hostname,
        limits,
        str(parsed.port) if parsed.port else None,
    )
    if not allowed:
        print_warning(validation_error)
        return f"Error: {validation_error}"

    cache_key = f"fetch_url:{normalized}"
    cached = get_cached_text(cache_key)
    if cached:
        return cached

    if http_client is not None:
        jina_error: str | None = None
        try:
            jina_response = http_client.get(
                f"https://r.jina.ai/{normalized}",
                headers={"X-Return-Format": "markdown"},
            )
            jina_text = jina_response.text()
            if jina_text and len(jina_text) > 50:
                result = _result_envelope(
                    success=True,
                    source={
                        "tool": "fetch_url",
                        "url": normalized,
                        "strategy": "jina_ai",
                    },
                    data=_truncate(jina_text),
                    message="Fetched content using Jina reader",
                )
                set_cached_text(cache_key, result)
                return result
        except HttpClientError as exc:
            jina_error = str(exc)

        try:
            page_response = http_client.get(
                normalized,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            charset = getattr(page_response.headers, "get_content_charset", lambda: None)() or "utf-8"
            html_content = page_response.body.decode(charset, errors="ignore")
        except HttpClientError as exc:
            error_msg = jina_error or str(exc)
            return _result_envelope(
                success=False,
                source={"tool": "fetch_url", "url": normalized},
                error=f"Error fetching URL: {error_msg}",
            )

        parser = StructuredHTMLParser()
        parser.feed(html_content)
        text = parser.get_text() or "No readable text content found."
        header = f"{parser.title}\n{'=' * len(parser.title)}\n\n" if parser.title else ""
        formatted = _truncate(f"{header}{text}\n\nSource: {normalized}".strip())
        result = _result_envelope(
            success=True,
            source={
                "tool": "fetch_url",
                "url": normalized,
                "strategy": "html_parser",
                "title": parser.title,
            },
            data=formatted,
        )
        set_cached_text(cache_key, result)
        return result
    def _size_error(length: int | None) -> str:
        cap_description = f"{max_chars} bytes" if max_chars else "configured limit"
        if length is None:
            return _validation_error(
                f"Response size exceeded maximum allowed ({cap_description})."
            )
        return _validation_error(
            f"Response too large ({length} bytes exceeds limit of {cap_description})."
        )

    def _read_response_body(response) -> tuple[bytes, str | None, str]:
        """Read a response body with a hard byte cap."""

        encoding = response.headers.get_content_charset() or "utf-8"
        if max_bytes:
            header_length = getattr(response.headers, "get", lambda *_a, **_k: None)(
                "Content-Length"
            )
            if header_length:
                try:
                    parsed_length = int(header_length)
                    if parsed_length > max_bytes:
                        return b"", _size_error(parsed_length), encoding
                except ValueError:
                    pass

        buffer = bytearray()
        chunk_size = 8192
        while True:
            to_read = max(1, min(chunk_size, max_bytes - len(buffer))) if max_bytes else chunk_size
            try:
                next_chunk = response.read(to_read)
            except TypeError:
                next_chunk = response.read()
            if not next_chunk:
                break
            buffer.extend(next_chunk)
            if max_bytes and len(buffer) >= max_bytes:
                try:
                    extra = response.read(1)
                except TypeError:
                    extra = response.read()
                if extra:
                    return bytes(buffer[:max_bytes]), _size_error(None), encoding
                buffer = buffer[:max_bytes]
                break
            if len(next_chunk) < to_read:
                break

        return bytes(buffer), None, encoding

    def _decode_body(body: bytes, encoding: str) -> str:
        return body.decode(encoding, errors="ignore")

    # Try Jina AI Reader first (optimized for LLM, returns clean markdown)
    for attempt in range(retries + 1):
        try:
            jina_url = f"https://r.jina.ai/{normalized}"
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; orun/1.0)",
                "X-Return-Format": "markdown",
            }

            req = urllib.request.Request(jina_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body, size_error, encoding = _read_response_body(response)
                if size_error:
                    return size_error

                content = _decode_body(body, encoding)

                if content and len(content) > 50:
                    content = _truncate(content)
                    result = (
                        f"{content}\n\nSource: {normalized} (via Jina AI Reader)"
                    ).strip()
                    set_cached_text(cache_key, result)
                    return result
        except Exception:
            if attempt < retries:
                time.sleep(1)
            continue

    # Fallback: Custom HTML parser
    for attempt in range(retries + 1):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            req = urllib.request.Request(normalized, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body, size_error, encoding = _read_response_body(response)
                if size_error:
                    return size_error
                html_content = _decode_body(body, encoding)
            break
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue
            return f"Error fetching URL: {str(e)}"

    parser = StructuredHTMLParser()
    parser.feed(html_content)
    text = parser.get_text() or "No readable text content found."

    if parser.title:
        header = f"{parser.title}\n{'=' * len(parser.title)}\n\n"
    else:
        header = ""

    formatted = _truncate(f"{header}{text}\n\nSource: {normalized}".strip())
    set_cached_text(cache_key, formatted)
    return formatted


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
        arxiv_id = (
            arxiv_id.strip()
            .replace("https://arxiv.org/abs/", "")
            .replace("http://arxiv.org/abs/", "")
        )
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


def web_search(query: str, max_results: int = 5, http_client: HttpClient | None = None) -> str:
    """
    Search the web using Google Custom Search API (with DuckDuckGo fallback).
    Detects query language and returns region-appropriate results.
    """
    limits = orun_config.get_section("limits")
    try:
        max_limit = limits.get("web_search_max_results", 5)
        max_results = min(int(max_results), int(max_limit))
    except (ValueError, TypeError):
        max_results = limits.get("web_search_max_results", 5)

    cache_key = f"web_search:{query}:{max_results}"
    cached = get_cached_text(cache_key)
    if cached:
        return cached

    timeout = limits.get("fetch_timeout_seconds", 20)
    retries = limits.get("web_search_retry_count", 1)
    backoff = limits.get("web_search_backoff_seconds", 1.0)
    client = http_client or _get_http_client(timeout, retries, backoff)
    last_error: str | None = None

    if search_config.has_google_credentials():
        params = urllib.parse.urlencode(
            {
                "key": search_config.google_api_key,
                "cx": search_config.google_cse_id,
                "q": query,
                "num": max_results,
            }
        )
        url = f"https://www.googleapis.com/customsearch/v1?{params}"
        try:
            response = client.get(url)
            payload = response.text()
            data = json.loads(payload)
            items = data.get("items", [])
            results = [
                {
                    "title": item.get("title", "No title"),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", "No description"),
                }
                for item in items[:max_results]
            ]
            message = None
            if not results:
                message = f"No results found for query: {query}"
            result = _result_envelope(
                success=True,
                source={"tool": "web_search", "provider": "google", "query": query},
                data=results,
                message=message,
            )
            set_cached_text(cache_key, result)
            return result
        except json.JSONDecodeError as exc:
            last_error = f"Malformed search response: {exc}"
        except HttpClientError as exc:
            last_error = str(exc)

    def detect_language(text: str) -> str:
        """Detect language and return appropriate DuckDuckGo region code."""
        LANG_TO_REGION = {
            "uk": "ua-uk",
            "ru": "ru-ru",
            "en": "us-en",
            "de": "de-de",
            "fr": "fr-fr",
            "es": "es-es",
            "it": "it-it",
            "pt": "pt-br",
            "pl": "pl-pl",
            "nl": "nl-nl",
            "ja": "jp-jp",
            "ko": "kr-kr",
            "zh-cn": "cn-zh",
            "zh-tw": "tw-tzh",
        }

        try:
            lang = detect(text)
            return LANG_TO_REGION.get(lang, "us-en")
        except (LangDetectException, Exception):
            return "us-en"

    try:
        region = detect_language(query)
        ddgs = DDGS()
        results = list(ddgs.text(query, region=region, max_results=max_results))

        formatted_results = [
            {
                "title": result.get("title", "No title"),
                "url": result.get("href", result.get("link", "")),
                "snippet": result.get("body", result.get("snippet", "No description")),
            }
            for result in results
        ]

        message = None
        if not formatted_results:
            message = f"No results found for query: {query}"

        result = _result_envelope(
            success=True,
            source={"tool": "web_search", "provider": "duckduckgo", "query": query},
            data=formatted_results,
            message=message,
        )
        set_cached_text(cache_key, result)
        return result

    except Exception as exc:
        if last_error:
            return _result_envelope(
                success=False,
                source={"tool": "web_search", "query": query},
                error=f"Error performing web search: {last_error}",
            )
        return _result_envelope(
            success=False,
            source={"tool": "web_search", "query": query},
            error=f"Error performing web search: {exc}",
        )

# --- Git Integration Tools ---


def git_status() -> str:
    """Get git status of the current repository."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "-b"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return f"Git error: {result.stderr.strip()}"

        output = result.stdout.strip()
        if not output:
            return "Working directory clean, nothing to commit."

        # Parse the output for better formatting
        lines = output.split("\n")
        branch_line = lines[0] if lines else ""
        changes = lines[1:] if len(lines) > 1 else []

        formatted = [f"**Branch:** {branch_line.replace('## ', '')}"]
        if changes:
            formatted.append(f"\n**Changes ({len(changes)} files):**")
            for change in changes[:20]:  # Limit to 20 files
                formatted.append(f"  {change}")
            if len(changes) > 20:
                formatted.append(f"  ... and {len(changes) - 20} more files")
        else:
            formatted.append("\nNo uncommitted changes.")

        return "\n".join(formatted)

    except subprocess.TimeoutExpired:
        return "Error: git status timed out"
    except FileNotFoundError:
        return "Error: git is not installed or not in PATH"
    except Exception as e:
        return f"Error running git status: {str(e)}"


def git_diff(file_path: str | None = None, staged: bool = False) -> str:
    """Get git diff for changes. Can specify a file or get all changes."""
    try:
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--staged")
        if file_path:
            cmd.append("--")
            cmd.append(file_path)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return f"Git error: {result.stderr.strip()}"

        output = result.stdout.strip()
        if not output:
            scope = f"for '{file_path}'" if file_path else ""
            stage = "staged " if staged else ""
            return f"No {stage}changes {scope}".strip()

        # Truncate if too long
        if len(output) > 10000:
            output = output[:10000] + "\n\n... (diff truncated, too large)"

        return output

    except subprocess.TimeoutExpired:
        return "Error: git diff timed out"
    except FileNotFoundError:
        return "Error: git is not installed or not in PATH"
    except Exception as e:
        return f"Error running git diff: {str(e)}"


def git_log(count: int = 10) -> str:
    """Get recent git commits."""
    try:
        count = min(count, 50)  # Limit to 50 commits
        result = subprocess.run(
            ["git", "log", f"-{count}", "--oneline", "--decorate"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return f"Git error: {result.stderr.strip()}"

        output = result.stdout.strip()
        if not output:
            return "No commits found."

        return f"**Recent commits ({count}):**\n\n{output}"

    except subprocess.TimeoutExpired:
        return "Error: git log timed out"
    except FileNotFoundError:
        return "Error: git is not installed or not in PATH"
    except Exception as e:
        return f"Error running git log: {str(e)}"


def git_commit(message: str, add_all: bool = False) -> str:
    """Create a git commit with the given message. Optionally add all changes first."""
    try:
        # Optionally add all changes
        if add_all:
            add_result = subprocess.run(
                ["git", "add", "-A"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if add_result.returncode != 0:
                return f"Git add error: {add_result.stderr.strip()}"

        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if (
                "nothing to commit" in stderr.lower()
                or "nothing to commit" in result.stdout.lower()
            ):
                return "Nothing to commit, working tree clean."
            return f"Git commit error: {stderr}"

        return f"Committed successfully:\n{result.stdout.strip()}"

    except subprocess.TimeoutExpired:
        return "Error: git commit timed out"
    except FileNotFoundError:
        return "Error: git is not installed or not in PATH"
    except Exception as e:
        return f"Error running git commit: {str(e)}"


# --- Code Execution Tool ---


def execute_python(code: str) -> str:
    """Execute Python code in a subprocess and return the output."""
    try:
        limits = orun_config.get_section("limits")
        timeout = limits.get("python_timeout_seconds", 30)
        max_chars = limits.get("python_output_limit", 12000)
        # Run Python code in a subprocess with timeout
        result = subprocess.run(
            ["python", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )

        output_parts = []

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if max_chars and len(stdout) > max_chars:
            stdout = stdout[:max_chars] + "\n... (truncated)"
        if max_chars and len(stderr) > max_chars:
            stderr = stderr[:max_chars] + "\n... (truncated)"

        if stdout:
            output_parts.append(f"**Output:**\n```\n{stdout}\n```")

        if stderr:
            output_parts.append(f"**Errors:**\n```\n{stderr}\n```")

        if result.returncode != 0:
            output_parts.append(f"**Exit code:** {result.returncode}")

        if not output_parts:
            return "Code executed successfully (no output)."

        return "\n\n".join(output_parts)

    except subprocess.TimeoutExpired:
        return "Error: Code execution timed out (30 second limit)"
    except FileNotFoundError:
        return "Error: Python interpreter not found"
    except Exception as e:
        return f"Error executing code: {str(e)}"


def call_function_model(task_description: str, context: str = "") -> str:
    """
    Delegate tool operations to FunctionGemma specialist model.
    """
    from orun import core as core_module

    return core_module.run_function_gemma_task(task_description, context)

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
    "git_status": git_status,
    "git_diff": git_diff,
    "git_log": git_log,
    "git_commit": git_commit,
    "execute_python": execute_python,
    "call_function_model": call_function_model,
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
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Get the current git status showing branch and changed files.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show git diff for uncommitted changes. Can view all changes or specific file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Optional: specific file to diff (default: all changes)",
                    },
                    "staged": {
                        "type": "boolean",
                        "description": "If true, show staged changes only (default: false)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Show recent git commits with hash and message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of commits to show (default: 10, max: 50)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Create a git commit with the given message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The commit message",
                    },
                    "add_all": {
                        "type": "boolean",
                        "description": "If true, stage all changes before committing (git add -A)",
                    },
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": "Execute Python code and return the output. Use for calculations, data processing, or testing code snippets. Has a 30-second timeout.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The Python code to execute",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_function_model",
            "description": "Delegate complex tool operations to FunctionGemma specialist model. Use this for any file operations, shell commands, searches, or code execution. The specialist model will handle the actual tool calls.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Clear description of what needs to be done (e.g., 'Read src/main.py and find all TODO comments', 'Run tests and report results')",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional: Additional context or background information",
                    },
                },
                "required": ["task_description"],
            },
        },
    },
]


def get_tools_for_model(model_name: str) -> list:
    """
    Get appropriate tools for a specific model.

    Logic:
    - FunctionGemma models: get all real tools (except call_function_model)
    - Regular models: only get call_function_model

    This ensures all tool operations go through FunctionGemma specialist.

    Args:
        model_name: Name of the model

    Returns:
        List of tool definitions appropriate for this model
    """
    is_function_gemma = (
        "functiongemma" in model_name.lower() or "function-gemma" in model_name.lower()
    )

    if is_function_gemma:
        # FunctionGemma gets all tools EXCEPT call_function_model
        return [
            tool
            for tool in TOOL_DEFINITIONS
            if tool["function"]["name"] != "call_function_model"
        ]
    else:
        # Regular models only get call_function_model
        return [
            tool
            for tool in TOOL_DEFINITIONS
            if tool["function"]["name"] == "call_function_model"
        ]
