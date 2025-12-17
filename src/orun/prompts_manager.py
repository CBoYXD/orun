import os
from dataclasses import dataclass
from pathlib import Path

from orun.utils import print_error


def _candidate_data_dirs() -> list[Path]:
    """Return possible locations for packaged or local prompt data."""
    candidates: list[Path] = []

    # User override
    env_dir = os.environ.get("ORUN_DATA_DIR")
    if env_dir:
        candidates.append(Path(env_dir))

    # Packaged data (when distributed via wheel)
    candidates.append(Path(__file__).resolve().parent / "data")

    # Repo-root data (local dev layout: repo/data next to src/)
    candidates.append(Path(__file__).resolve().parents[2] / "data")

    # Current working directory (fallback)
    candidates.append(Path.cwd() / "data")

    return candidates


def _resolve_data_dir(kind: str) -> Path:
    """Find the first existing directory for the given kind (prompts/strategies)."""
    for base in _candidate_data_dirs():
        candidate = base / kind
        if candidate.exists():
            return candidate
    # Default to repo-style path even if missing so callers can still build paths
    return Path("data") / kind


PROMPTS_DIR = _resolve_data_dir("prompts")
STRATEGIES_DIR = _resolve_data_dir("strategies")
ROLES_DIR = PROMPTS_DIR / "roles"


@dataclass
class PromptBuild:
    """Result of composing user input with prompt/strategy templates."""

    text: str
    applied_prompt: str | None
    applied_strategy: str | None
    missing: list[str]


def get_prompt(name: str) -> str:
    """Loads a prompt from the prompts directory, checking roles subdir if applicable."""
    # Try exact match in main prompts dir
    path = PROMPTS_DIR / name
    if not path.exists() and not name.endswith(".md"):
        path = PROMPTS_DIR / f"{name}.md"

    # If not found, try in roles subdir
    if not path.exists():
        path = ROLES_DIR / name
        if not path.exists() and not name.endswith(".md"):
            path = ROLES_DIR / f"{name}.md"

    if path.exists():
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception as e:
            print_error(f"Failed to load prompt '{name}': {e}")
            return ""

    return ""


def get_strategy(name: str) -> str:
    """Loads a strategy from the strategies directory."""
    path = STRATEGIES_DIR / name

    # Try .md first
    if not path.exists() and not name.endswith((".md", ".json")):
        path = STRATEGIES_DIR / f"{name}.md"

    # If not .md, try .json
    if not path.exists():
        path = STRATEGIES_DIR / f"{name}.json"

    if path.exists():
        try:
            content = path.read_text(encoding="utf-8").strip()
            # If it's JSON, try to extract the relevant text
            if path.suffix == ".json":
                import json

                try:
                    data = json.loads(content)
                    # Handle different JSON structures
                    if "prompt" in data:
                        return data["prompt"]
                    elif "description" in data:
                        return data["description"]
                    elif "strategy" in data:
                        return data["strategy"]
                    elif isinstance(data, str):
                        return data
                    else:
                        # Return a description of the strategy
                        return f"Strategy: {name}\n\n{json.dumps(data, indent=2)}"
                except json.JSONDecodeError:
                    return content
            return content
        except Exception as e:
            print_error(f"Failed to load strategy '{name}': {e}")
            return ""

    return ""


def list_prompts() -> list[str]:
    """Lists available prompt files, including those in roles subdirectory."""
    prompts = []
    if PROMPTS_DIR.exists():
        prompts.extend([p.stem for p in PROMPTS_DIR.glob("*.md")])
    if ROLES_DIR.exists():
        prompts.extend([f"role/{p.stem}" for p in ROLES_DIR.glob("*.md")])
    return sorted(prompts)


def list_strategies() -> list[str]:
    """Lists available strategy files (both .md and .json)."""
    strategies = []
    if STRATEGIES_DIR.exists():
        strategies.extend([p.stem for p in STRATEGIES_DIR.glob("*.md")])
        strategies.extend([p.stem for p in STRATEGIES_DIR.glob("*.json")])
    # Remove duplicates while preserving order
    return sorted(list(set(strategies)))


def compose_prompt(
    user_prompt: str,
    prompt_template: str | None = None,
    strategy_template: str | None = None,
) -> PromptBuild:
    """Combine user text with selected prompt/strategy templates."""
    parts: list[str] = []
    missing: list[str] = []
    applied_prompt: str | None = None
    applied_strategy: str | None = None

    if prompt_template:
        prompt_text = get_prompt(prompt_template)
        if prompt_text:
            parts.append(prompt_text.strip())
            applied_prompt = prompt_template
        else:
            missing.append(f"prompt '{prompt_template}'")

    if user_prompt:
        parts.append(user_prompt.strip())

    if strategy_template:
        strategy_text = get_strategy(strategy_template)
        if strategy_text:
            parts.append(strategy_text.strip())
            applied_strategy = strategy_template
        else:
            missing.append(f"strategy '{strategy_template}'")

    full_text = "\n\n".join(part for part in parts if part)

    return PromptBuild(
        text=full_text,
        applied_prompt=applied_prompt,
        applied_strategy=applied_strategy,
        missing=missing,
    )
