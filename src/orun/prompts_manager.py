from pathlib import Path

from orun.utils import print_error

PROMPTS_DIR = Path("data/prompts")
STRATEGIES_DIR = Path("data/strategies")
ROLES_DIR = PROMPTS_DIR / "roles"


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
