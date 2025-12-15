import re
import sys
from pathlib import Path

def bump_version(version_str):
    parts = list(map(int, version_str.split('.')))
    if len(parts) != 3:
        raise ValueError("Version must be X.Y.Z")
        
    major, minor, patch = parts
    
    # Custom rule: X.Y.9 -> X.(Y+1).0
    if patch == 9:
        minor += 1
        patch = 0
    else:
        patch += 1
        
    return f"{major}.{minor}.{patch}"

def main():
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        print("Error: pyproject.toml not found", file=sys.stderr)
        sys.exit(1)
        
    content = pyproject_path.read_text(encoding="utf-8")
    
    # Regex to find version = "x.y.z"
    # Matches: version = "1.2.3" or version="1.2.3"
    match = re.search(r'version\s*=\s*"(\d+\.\d+\.\d+)"', content)
    if not match:
        print("Error: Could not find version in pyproject.toml", file=sys.stderr)
        sys.exit(1)
        
    current_version = match.group(1)
    new_version = bump_version(current_version)
    
    # Replace only the first occurrence (which should be the package version)
    new_content = content.replace(f'version = "{current_version}"', f'version = "{new_version}"', 1)
    pyproject_path.write_text(new_content, encoding="utf-8")
    
    print(f"Bumped version: {current_version} -> {new_version}")

if __name__ == "__main__":
    main()
