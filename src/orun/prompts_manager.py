from pathlib import Path
from orun.utils import print_error

PROMPTS_DIR = Path("prompts")
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

def list_prompts() -> list[str]:
    """Lists available prompt files, including those in roles subdirectory."""
    prompts = []
    if PROMPTS_DIR.exists():
        prompts.extend([p.stem for p in PROMPTS_DIR.glob("*.md")])
    if ROLES_DIR.exists():
        prompts.extend([f"role/{p.stem}" for p in ROLES_DIR.glob("*.md")])
    return sorted(prompts)
