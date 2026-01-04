import json
import os
from pathlib import Path

from orun.rich_utils import Colors, console

DEFAULT_LIMITS = {
    "shell_timeout_seconds": 20,
    "shell_output_limit": 12000,
    "fetch_timeout_seconds": 20,
    "fetch_max_chars": 15000,
    "fetch_retry_count": 1,
    "fetch_allow_hosts": [],
    "fetch_block_hosts": ["localhost", "127.0.0.1", "::1"],
    "fetch_block_private_networks": True,
    "web_search_max_results": 5,
    "web_search_retry_count": 1,
    "python_timeout_seconds": 30,
    "python_output_limit": 12000,
    "file_read_max_chars": 200000,
    "tool_preview_chars": 200,
}

DEFAULT_SANDBOX = {
    "enabled": True,
    "allowed_roots": ["<cwd>"],
}

DEFAULT_CACHE = {
    "enabled": True,
    "ttl_seconds": 3600,
    "max_entries": 200,
}

DEFAULT_DB = {
    "max_size_mb": 10,
    "cleanup_fraction": 0.10,
    "min_age_days": 0.1,
}

DEFAULT_CONTEXT = {
    "max_files": 50,
    "scan_limit": 300,
    "file_max_chars": 20000,
    "total_chars": 80000,
}

DEFAULT_SHELL = {
    "allowlist": [],
    "denylist": [],
}

DEFAULTS = {
    "limits": DEFAULT_LIMITS,
    "sandbox": DEFAULT_SANDBOX,
    "cache": DEFAULT_CACHE,
    "db": DEFAULT_DB,
    "context": DEFAULT_CONTEXT,
    "shell": DEFAULT_SHELL,
}


def get_config_path() -> Path:
    override = os.getenv("ORUN_CONFIG_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".orun" / "config.json"


def load_config() -> dict:
    config_path = get_config_path()
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        console.print(f"Warning: Could not load config: {e}", style=Colors.YELLOW)
        return {}


def save_config(config: dict) -> None:
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def ensure_defaults() -> dict:
    config = load_config()
    changed = False
    for section, defaults in DEFAULTS.items():
        existing = config.get(section)
        if existing is None:
            config[section] = defaults.copy()
            changed = True
            continue
        if not isinstance(existing, dict):
            config[section] = defaults.copy()
            changed = True
            continue
        for key, value in defaults.items():
            if key not in existing:
                existing[key] = value
                changed = True
    if changed:
        save_config(config)
    return config


def get_section(name: str) -> dict:
    config = load_config()
    defaults = DEFAULTS.get(name, {})
    section = config.get(name, {})
    if not isinstance(section, dict):
        section = {}
    merged = defaults.copy()
    merged.update(section)
    return merged
