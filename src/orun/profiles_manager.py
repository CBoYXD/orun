"""
Profile manager for orun.
Profiles are collections of prompt templates that get activated together.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from orun.rich_utils import print_error


def _candidate_data_dirs() -> list[Path]:
    """Return possible locations for profile data."""
    candidates: list[Path] = []

    # User custom data (~/.orun/data/)
    candidates.append(Path.home() / ".orun" / "data")

    # Packaged data (when distributed via wheel)
    candidates.append(Path(__file__).resolve().parent / "data")

    # Repo-root data (local dev layout: repo/data next to src/)
    candidates.append(Path(__file__).resolve().parents[2] / "data")

    # Current working directory (fallback)
    candidates.append(Path.cwd() / "data")

    return candidates


def _resolve_data_dirs(kind: str) -> list[Path]:
    """Find all existing directories for the given kind."""
    dirs = []
    for base in _candidate_data_dirs():
        candidate = base / kind
        if candidate.exists():
            dirs.append(candidate)
    if not dirs:
        dirs.append(Path("data") / kind)
    return dirs


PROFILES_DIRS = _resolve_data_dirs("profiles")
PROFILES_DIR = PROFILES_DIRS[0] if PROFILES_DIRS else Path("data") / "profiles"


@dataclass
class Profile:
    """A profile containing a list of prompt templates to activate."""
    name: str
    description: str
    included_prompts: list[str] = field(default_factory=list)
    strategy: str | None = None
    options: dict | None = None


def get_profile(name: str) -> Profile | None:
    """Load a profile by name from profiles directories."""
    for profiles_dir in PROFILES_DIRS:
        json_path = profiles_dir / f"{name}.json"
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                return Profile(
                    name=name,
                    description=data.get("description", ""),
                    included_prompts=data.get("included_prompts", data.get("prompts", [])),
                    strategy=data.get("strategy"),
                    options=data.get("options"),
                )
            except Exception as e:
                print_error(f"Failed to load profile '{name}': {e}")
                return None

    return None


def list_profiles() -> list[dict]:
    """List all available profiles from all directories."""
    profiles = {}  # Use dict to deduplicate by name

    for profiles_dir in PROFILES_DIRS:
        if not profiles_dir.exists():
            continue

        for json_file in profiles_dir.glob("*.json"):
            name = json_file.stem
            if name not in profiles:
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    prompts_list = data.get("included_prompts", data.get("prompts", []))
                    profiles[name] = {
                        "name": name,
                        "description": data.get("description", "No description"),
                        "prompts_count": len(prompts_list),
                        "included_prompts": prompts_list,
                        "source": "user" if ".orun" in str(profiles_dir) else "default",
                    }
                except Exception:
                    profiles[name] = {
                        "name": name,
                        "description": "Error loading profile",
                        "prompts_count": 0,
                        "prompts": [],
                        "source": "user" if ".orun" in str(profiles_dir) else "default",
                    }

    return sorted(profiles.values(), key=lambda x: x["name"])


def create_profile(name: str, included_prompts: list[str], description: str = "", strategy: str | None = None) -> bool:
    """Create a new profile in user directory."""
    user_profiles_dir = Path.home() / ".orun" / "data" / "profiles"
    user_profiles_dir.mkdir(parents=True, exist_ok=True)

    profile_path = user_profiles_dir / f"{name}.json"

    try:
        data = {
            "description": description or f"Custom profile: {name}",
            "included_prompts": included_prompts,
        }
        if strategy:
            data["strategy"] = strategy
        profile_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as e:
        print_error(f"Failed to create profile '{name}': {e}")
        return False
