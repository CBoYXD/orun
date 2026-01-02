import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from orun.rich_utils import Colors, console, print_error


def get_plugins_dir() -> Path:
    """Return the directory that stores user MCP plugins."""
    return Path.home() / ".orun" / "mcps"


def _load_module(path: Path) -> ModuleType | None:
    """Safely load a module from a path without polluting the module namespace."""
    module_name = f"orun_mcp_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        print_error(f"Skipping MCP plugin {path.name}: unable to create loader")
        return None

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        print_error(f"Failed to import MCP plugin {path.name}: {exc}")
        return None
    return module


def _call_register(module: ModuleType, app: Any, path: Path) -> bool:
    """Invoke a register hook if it exists on a module."""
    for attr in ("register_mcp", "register"):
        register_fn = getattr(module, attr, None)
        if callable(register_fn):
            try:
                register_fn(app)
            except Exception as exc:
                print_error(f"Error while initializing MCP plugin {path.name}: {exc}")
                return False
            return True

    console.print(
        f"⚠️  MCP plugin {path.name} is missing a register(app) or register_mcp(app) function",
        style=Colors.YELLOW,
    )
    return False


def load_user_mcp_plugins(app: Any) -> list[Path]:
    """
    Load user-provided MCP plugins from ~/.orun/mcps.

    Each plugin should be a Python file that exposes a callable `register(app)`
    or `register_mcp(app)` function. The given `app` is the Robyn instance used
    by the builtin MCP server, so plugins can declare tools/resources via
    `app.mcp`.
    """
    plugins_dir = get_plugins_dir()
    plugins_dir.mkdir(parents=True, exist_ok=True)

    if not hasattr(app, "mcp"):
        console.print(
            "Current Robyn install does not expose the MCP API; skipping plugin loading.",
            style=Colors.YELLOW,
        )
        return []

    plugin_paths = [
        path
        for path in sorted(plugins_dir.rglob("*.py"))
        if path.name != "__init__.py" and "__pycache__" not in path.parts
    ]

    if not plugin_paths:
        console.print(f"No MCP plugins found in {plugins_dir}", style=Colors.GREY)
        return []

    loaded: list[Path] = []
    sys.path.insert(0, str(plugins_dir))
    try:
        for path in plugin_paths:
            module = _load_module(path)
            if not module:
                continue
            if _call_register(module, app, path):
                loaded.append(path)
                console.print(
                    f"🔌 Loaded MCP plugin: {path.relative_to(plugins_dir)}",
                    style=Colors.GREEN,
                )
    finally:
        try:
            sys.path.remove(str(plugins_dir))
        except ValueError:
            pass

    if not loaded:
        console.print("No MCP plugins were activated.", style=Colors.YELLOW)

    return loaded
