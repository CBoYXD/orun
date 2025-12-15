import sys
import subprocess
import re
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: python git_commit_release.py <message>")
        sys.exit(1)
        
    # Join all args to handle spaces if passed loosely, though quotes in justfile handle it
    msg = " ".join(sys.argv[1:])
    
    try:
        content = Path("pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'version\s*=\s*"(\d+\.\d+\.\d+)"', content)
        if not match:
            print("Error: version not found in pyproject.toml")
            sys.exit(1)
            
        version = match.group(1)
        commit_msg = f"Update to {version}. Changes: {msg}"
        
        print(f"Committing with message: {commit_msg}")
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
