"""Rich utilities for enhanced terminal output."""

import sys
from typing import Any, Optional

from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

# Create a console instance with emoji support disabled for Windows
if sys.platform == "win32":
    console = Console(stderr=True)
else:
    console = Console(stderr=True)


class Colors:
    """Color constants for Rich."""

    RED = "red"
    GREEN = "green"
    YELLOW = "yellow"
    BLUE = "blue"
    MAGENTA = "magenta"
    CYAN = "cyan"
    WHITE = "white"
    BLACK = "black"
    GREY = "bright_black"
    BOLD_RED = "bold red"
    BOLD_GREEN = "bold green"
    BOLD_YELLOW = "bold yellow"
    BOLD_BLUE = "bold blue"
    BOLD_MAGENTA = "bold magenta"
    BOLD_CYAN = "bold cyan"
    BOLD_WHITE = "bold white"
    DIM = "dim"
    ITALIC = "italic"


def colored(text: str, color: str) -> str:
    """Return text with Rich color markup."""
    return f"[{color}]{text}[/{color.split()[0]}]"


def print_error(message: str) -> None:
    """Print an error message with Rich formatting."""
    console.print(f"❌ {message}", style=Colors.RED)


def print_success(message: str) -> None:
    """Print a success message with Rich formatting."""
    console.print(f"✅ {message}", style=Colors.GREEN)


def print_warning(message: str) -> None:
    """Print a warning message with Rich formatting."""
    console.print(f"⚠️  {message}", style=Colors.YELLOW)


def print_info(message: str) -> None:
    """Print an info message with Rich formatting."""
    console.print(message, style=Colors.CYAN)


def create_table(title: str, columns: list[str]) -> Table:
    """Create a Rich table with the given columns."""
    table = Table(title=title, show_header=True, header_style=Colors.BOLD_MAGENTA)
    for col in columns:
        table.add_column(col, style=Colors.CYAN)
    return table


def print_table(table: Table) -> None:
    """Print a Rich table."""
    console.print(table)


def create_panel(content: Any, title: str = "", style: str = Colors.BLUE) -> Panel:
    """Create a Rich panel."""
    return Panel(content, title=title, border_style=style)


def print_panel(panel: Panel) -> None:
    """Print a Rich panel."""
    console.print(panel)


def create_spinner_progress(description: str = "Working...") -> Progress:
    """Create a Rich progress spinner."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    )


def create_bar_progress(description: str = "Processing...") -> Progress:
    """Create a Rich progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        transient=True,
        console=console,
    )


def print_markdown(content: str) -> None:
    """Print Markdown content with Rich formatting."""
    md = Markdown(content)
    console.print(md)


def print_code(code: str, language: str = "python", theme: str = "monokai") -> None:
    """Print code with syntax highlighting."""
    syntax = Syntax(code, language, theme=theme)
    console.print(syntax)


def create_tree(label: str) -> Tree:
    """Create a Rich tree."""
    return Tree(f"[bold]{label}[/bold]")


def print_columns(items: list, equal: bool = False, expand: bool = False) -> None:
    """Print items in columns."""
    columns = Columns(items, equal=equal, expand=expand)
    console.print(columns)


def prompt_input(
    message: str, default: Optional[str] = None, password: bool = False
) -> str:
    """Prompt for user input."""
    return Prompt.ask(message, default=default, password=password)


def confirm(message: str, default: bool = True) -> bool:
    """Ask for confirmation."""
    return console.confirm(message, default=default)


def get_console_width() -> int:
    """Get the console width."""
    return console.width


def print_centered(text: str, style: str = Colors.WHITE) -> None:
    """Print centered text."""
    console.print(Align.center(Text(text, style=style)))


def clear_line() -> None:
    """Clear the current line."""
    console.clear()


# Initialize Rich console on import
if not console.is_terminal:
    # Fallback to basic print if not a terminal
    console = Console(force_terminal=False)
