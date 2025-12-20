import hashlib
import json
import time
from pathlib import Path

from orun import config as orun_config


def _cache_dir() -> Path:
    return Path.home() / ".orun" / "cache"


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return _cache_dir() / f"{digest}.json"


def _settings() -> dict:
    return orun_config.get_section("cache")


def get_cached_text(key: str) -> str | None:
    settings = _settings()
    if not settings.get("enabled", True):
        return None
    cache_path = _cache_path(key)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    created_at = payload.get("created_at")
    if not isinstance(created_at, (int, float)):
        return None
    ttl = settings.get("ttl_seconds", 0)
    if ttl and time.time() - created_at > ttl:
        return None
    return payload.get("value")


def set_cached_text(key: str, value: str) -> None:
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
    _prune_cache(cache_dir, settings.get("max_entries", 200))


def _prune_cache(cache_dir: Path, max_entries: int) -> None:
    if not max_entries:
        return
    try:
        files = sorted(cache_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    except Exception:
        return
    excess = len(files) - max_entries
    for path in files[: max(0, excess)]:
        try:
            path.unlink()
        except Exception:
            continue
