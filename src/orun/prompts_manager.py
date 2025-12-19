import json
from dataclasses import dataclass
from pathlib import Path

from orun.rich_utils import print_error


def _candidate_data_dirs() -> list[Path]:
    """Return possible locations for packaged or local prompt data."""
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
    """Find all existing directories for the given kind (prompts/strategies).
    Returns list of paths in priority order (user first, then defaults)."""
    dirs = []
    for base in _candidate_data_dirs():
        candidate = base / kind
        if candidate.exists():
            dirs.append(candidate)
    # Always include at least one path (for error messages, etc)
    if not dirs:
        dirs.append(Path("data") / kind)
    return dirs


# Get all possible directories (user custom will be first if it exists)
PROMPTS_DIRS = _resolve_data_dirs("prompts")
STRATEGIES_DIRS = _resolve_data_dirs("strategies")

# Primary directories for backward compatibility
PROMPTS_DIR = PROMPTS_DIRS[0]
STRATEGIES_DIR = STRATEGIES_DIRS[0]
ROLES_DIR = PROMPTS_DIR / "roles"


@dataclass
class PromptBuild:
    """Result of composing user input with prompt/strategy templates."""

    text: str
    applied_prompt: str | None
    applied_strategy: str | None
    missing: list[str]


def get_prompt(name: str) -> str:
    """Loads a prompt from the prompts directories (user custom first, then defaults)."""
    # Try all prompts directories in order
    for prompts_dir in PROMPTS_DIRS:
        # Try exact match in main prompts dir
        path = prompts_dir / name
        if not path.exists() and not name.endswith(".md"):
            path = prompts_dir / f"{name}.md"

        # If not found, try in roles subdir
        if not path.exists():
            roles_dir = prompts_dir / "roles"
            path = roles_dir / name
            if not path.exists() and not name.endswith(".md"):
                path = roles_dir / f"{name}.md"

        if path.exists():
            try:
                return path.read_text(encoding="utf-8").strip()
            except Exception as e:
                print_error(f"Failed to load prompt '{name}': {e}")
                return ""

    return ""


def get_strategy(name: str) -> str:
    """Loads a strategy from the strategies directories (user custom first, then defaults)."""
    # Try all strategies directories in order
    for strategies_dir in STRATEGIES_DIRS:
        path = strategies_dir / name

        # Try .md first
        if not path.exists() and not name.endswith((".md", ".json")):
            path = strategies_dir / f"{name}.md"

        # If not .md, try .json
        if not path.exists():
            path = strategies_dir / f"{name}.json"

        if path.exists():
            try:
                content = path.read_text(encoding="utf-8").strip()
                # If it's JSON, try to extract the relevant text
                if path.suffix == ".json":
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
    """Lists available prompt files from all directories (user custom + defaults)."""
    prompts = set()
    for prompts_dir in PROMPTS_DIRS:
        if prompts_dir.exists():
            prompts.update([p.stem for p in prompts_dir.glob("*.md")])
        roles_dir = prompts_dir / "roles"
        if roles_dir.exists():
            prompts.update([f"role/{p.stem}" for p in roles_dir.glob("*.md")])
    return sorted(prompts)


def list_strategies() -> list[str]:
    """Lists available strategy files from all directories (user custom + defaults)."""
    strategies = set()
    for strategies_dir in STRATEGIES_DIRS:
        if strategies_dir.exists():
            strategies.update([p.stem for p in strategies_dir.glob("*.md")])
            strategies.update([p.stem for p in strategies_dir.glob("*.json")])
    return sorted(strategies)


def compose_prompt(
    user_prompt: str,
    prompt_template: str | list[str] | None = None,
    strategy_template: str | list[str] | None = None,
) -> PromptBuild:
    """Combine user text with selected prompt/strategy templates."""
    parts: list[str] = []
    missing: list[str] = []
    applied_prompts: list[str] = []
    applied_strategies: list[str] = []

    # Handle prompt templates (single or multiple)
    prompt_templates = []
    if prompt_template:
        if isinstance(prompt_template, str):
            prompt_templates = [prompt_template]
        else:
            prompt_templates = prompt_template

    for template in prompt_templates:
        prompt_text = get_prompt(template)
        if prompt_text:
            parts.append(prompt_text.strip())
            applied_prompts.append(template)
        else:
            missing.append(f"prompt '{template}'")

    if user_prompt:
        parts.append(user_prompt.strip())

    # Handle strategy templates (single or multiple)
    strategy_templates = []
    if strategy_template:
        if isinstance(strategy_template, str):
            strategy_templates = [strategy_template]
        else:
            strategy_templates = strategy_template

    for template in strategy_templates:
        strategy_text = get_strategy(template)
        if strategy_text:
            parts.append(strategy_text.strip())
            applied_strategies.append(template)
        else:
            missing.append(f"strategy '{template}'")

    full_text = "\n\n".join(part for part in parts if part)

    return PromptBuild(
        text=full_text,
        applied_prompt=", ".join(applied_prompts) if applied_prompts else None,
        applied_strategy=", ".join(applied_strategies) if applied_strategies else None,
        missing=missing,
    )
