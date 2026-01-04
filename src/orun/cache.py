import hashlib
import json
import time
from pathlib import Path
from typing import Any

from orun import config as orun_config


def _cache_dir() -> Path:
    """Return the directory path used for caching."""

    return Path.home() / ".orun" / "cache"


def _cache_path(key: str) -> Path:
    """Return the full cache file path for the provided key."""

    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return _cache_dir() / f"{digest}.json"


def _settings() -> dict:
    """Fetch cache-related configuration settings."""

    return orun_config.get_section("cache")


def _safe_unlink(path: Path) -> None:
    """Attempt to remove the provided file, ignoring failures."""

    try:
        path.unlink()
    except FileNotFoundError:
        return
    except Exception:
        return


def _load_payload(cache_path: Path) -> dict[str, Any] | None:
    """Load a cache payload from disk, deleting invalid files."""

    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        _safe_unlink(cache_path)
        return None


def get_cached_text(key: str) -> str | None:
    """Retrieve a cached text value if present and still valid."""

    settings = _settings()
    if not settings.get("enabled", True):
        return None

    cache_path = _cache_path(key)
    if not cache_path.exists():
        return None

    payload = _load_payload(cache_path)
    if payload is None:
        return None

    created_at = payload.get("created_at")
    if not isinstance(created_at, (int, float)):
        _safe_unlink(cache_path)
        return None

    ttl_seconds = settings.get("ttl_seconds", 0)
    ttl_value = ttl_seconds if isinstance(ttl_seconds, (int, float)) else 0
    if ttl_value and time.time() - created_at > ttl_value:
        _safe_unlink(cache_path)
        return None

    value = payload.get("value")
    if not isinstance(value, str):
        _safe_unlink(cache_path)
        return None

    return value


def set_cached_text(key: str, value: str) -> None:
    """Persist a text value to cache if caching is enabled."""

    settings = _settings()
    if not settings.get("enabled", True):
        return

    cache_dir = _cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    payload = {"created_at": time.time(), "value": value}
    try:
        _cache_path(key).write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        return

    _prune_cache(
        cache_dir,
        settings.get("max_entries", 200),
        settings.get("ttl_seconds", 0),
    )


def _prune_cache(cache_dir: Path, max_entries: int, ttl_seconds: int | float) -> None:
    """
    Remove expired cache entries and prune the cache to the configured size.

    Files with invalid payloads or an expired ``created_at`` timestamp are
    removed first. The cache is then trimmed to ``max_entries`` using the oldest
    entries when necessary.
    """

    try:
        files = sorted(cache_dir.glob("*.json"), key=lambda path: path.stat().st_mtime)
    except Exception:
        return

    ttl_value = ttl_seconds if isinstance(ttl_seconds, (int, float)) else 0
    now = time.time()
    removed_count = 0
    retained_files: list[Path] = []

    for path in files:
        payload = _load_payload(path)
        if payload is None:
            removed_count += 1
            continue

        created_at = payload.get("created_at")
        if not isinstance(created_at, (int, float)):
            _safe_unlink(path)
            removed_count += 1
            continue

        if ttl_value and now - created_at > ttl_value:
            _safe_unlink(path)
            removed_count += 1
            continue

        retained_files.append(path)

    if max_entries and max_entries > 0:
        excess = len(retained_files) - max_entries
        for path in retained_files[: max(0, excess)]:
            _safe_unlink(path)
            removed_count += 1

    if removed_count > 1:
        print(f"[cache] Pruned {removed_count} stale cache entries")
