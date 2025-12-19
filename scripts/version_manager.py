#!/usr/bin/env python3
"""
Version manager for orun-py supporting PEP 440 version schemes.

Supports:
- Standard releases: 1.2.3
- Alpha: 1.2.3a1, 1.2.3a2
- Beta: 1.2.3b1, 1.2.3b2
- Release Candidate: 1.2.3rc1, 1.2.3rc2
- Post releases: 1.2.3.post1, 1.2.3.post2

Usage:
    python scripts/version_manager.py patch           # 1.2.3 -> 1.2.4
    python scripts/version_manager.py minor           # 1.2.3 -> 1.3.0
    python scripts/version_manager.py major           # 1.2.3 -> 2.0.0
    python scripts/version_manager.py alpha           # 1.2.3 -> 1.2.4a1 or 1.2.3a1 -> 1.2.3a2
    python scripts/version_manager.py beta            # 1.2.3 -> 1.2.4b1 or 1.2.3b1 -> 1.2.3b2
    python scripts/version_manager.py rc              # 1.2.3 -> 1.2.4rc1 or 1.2.3rc1 -> 1.2.3rc2
    python scripts/version_manager.py post            # 1.2.3 -> 1.2.3.post1
    python scripts/version_manager.py release         # 1.2.3a1 -> 1.2.3 (finalize pre-release)
    python scripts/version_manager.py set X.Y.Z       # Set specific version
"""

import re
import sys
from pathlib import Path


class Version:
    """Parse and manipulate PEP 440 versions."""

    def __init__(self, version_str: str):
        self.original = version_str
        self.major = 0
        self.minor = 0
        self.patch = 0
        self.pre_type = None  # 'a', 'b', 'rc'
        self.pre_number = None
        self.post = None

        self._parse(version_str)

    def _parse(self, version_str: str):
        # Regex for PEP 440: X.Y.Z[{a|b|rc}N][.postN]
        pattern = r'^(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?(\.post(\d+))?$'
        match = re.match(pattern, version_str)

        if not match:
            raise ValueError(f"Invalid version format: {version_str}")

        self.major = int(match.group(1))
        self.minor = int(match.group(2))
        self.patch = int(match.group(3))

        if match.group(4):  # Pre-release type
            self.pre_type = match.group(4)
            self.pre_number = int(match.group(5))

        if match.group(7):  # Post release
            self.post = int(match.group(7))

    def bump_major(self):
        """Bump major version: 1.2.3 -> 2.0.0"""
        return Version(f"{self.major + 1}.0.0")

    def bump_minor(self):
        """Bump minor version: 1.2.3 -> 1.3.0"""
        return Version(f"{self.major}.{self.minor + 1}.0")

    def bump_patch(self):
        """Bump patch version: 1.2.3 -> 1.2.4"""
        return Version(f"{self.major}.{self.minor}.{self.patch + 1}")

    def bump_alpha(self):
        """Bump to next alpha: 1.2.3 -> 1.2.4a1 or 1.2.3a1 -> 1.2.3a2"""
        if self.pre_type == 'a':
            # Already alpha, increment alpha number
            return Version(f"{self.major}.{self.minor}.{self.patch}a{self.pre_number + 1}")
        else:
            # New alpha for next patch
            next_patch = self.bump_patch()
            return Version(f"{next_patch.major}.{next_patch.minor}.{next_patch.patch}a1")

    def bump_beta(self):
        """Bump to next beta: 1.2.3 -> 1.2.4b1 or 1.2.3b1 -> 1.2.3b2"""
        if self.pre_type == 'b':
            # Already beta, increment beta number
            return Version(f"{self.major}.{self.minor}.{self.patch}b{self.pre_number + 1}")
        else:
            # New beta for next patch
            next_patch = self.bump_patch()
            return Version(f"{next_patch.major}.{next_patch.minor}.{next_patch.patch}b1")

    def bump_rc(self):
        """Bump to next rc: 1.2.3 -> 1.2.4rc1 or 1.2.3rc1 -> 1.2.3rc2"""
        if self.pre_type == 'rc':
            # Already rc, increment rc number
            return Version(f"{self.major}.{self.minor}.{self.patch}rc{self.pre_number + 1}")
        else:
            # New rc for next patch
            next_patch = self.bump_patch()
            return Version(f"{next_patch.major}.{next_patch.minor}.{next_patch.patch}rc1")

    def bump_post(self):
        """Bump to next post release: 1.2.3 -> 1.2.3.post1"""
        if self.post is not None:
            return Version(f"{self.major}.{self.minor}.{self.patch}.post{self.post + 1}")
        else:
            return Version(f"{self.major}.{self.minor}.{self.patch}.post1")

    def finalize(self):
        """Finalize pre-release: 1.2.3a1 -> 1.2.3"""
        return Version(f"{self.major}.{self.minor}.{self.patch}")

    def __str__(self):
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre_type and self.pre_number is not None:
            base += f"{self.pre_type}{self.pre_number}"
        if self.post is not None:
            base += f".post{self.post}"
        return base


def update_version_in_file(file_path: Path, old_version: str, new_version: str):
    """Update version string in a file."""
    if not file_path.exists():
        return False

    content = file_path.read_text(encoding="utf-8")

    # For pyproject.toml
    if file_path.name == "pyproject.toml":
        pattern = r'version\s*=\s*"[^"]+"'
        new_content = re.sub(pattern, f'version = "{new_version}"', content, count=1)
    # For __init__.py
    elif file_path.name == "__init__.py":
        pattern = r'__version__\s*=\s*"[^"]+"'
        if re.search(pattern, content):
            new_content = re.sub(pattern, f'__version__ = "{new_version}"', content)
        else:
            # Add version if it doesn't exist
            if content and not content.endswith("\n"):
                content += "\n"
            new_content = content + f'__version__ = "{new_version}"\n'
    else:
        return False

    if new_content != content:
        file_path.write_text(new_content, encoding="utf-8")
        return True
    return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    # Read current version
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        print("Error: pyproject.toml not found", file=sys.stderr)
        sys.exit(1)

    content = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'version\s*=\s*"([^"]+)"', content)
    if not match:
        print("Error: Could not find version in pyproject.toml", file=sys.stderr)
        sys.exit(1)

    current_version_str = match.group(1)

    try:
        current_version = Version(current_version_str)
    except ValueError as e:
        print(f"Error parsing current version: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine new version based on command
    if command == "set":
        if len(sys.argv) < 3:
            print("Error: 'set' requires a version argument", file=sys.stderr)
            sys.exit(1)
        try:
            new_version = Version(sys.argv[2])
        except ValueError as e:
            print(f"Error: Invalid version format: {e}", file=sys.stderr)
            sys.exit(1)
    elif command == "major":
        new_version = current_version.bump_major()
    elif command == "minor":
        new_version = current_version.bump_minor()
    elif command == "patch":
        new_version = current_version.bump_patch()
    elif command == "alpha" or command == "a":
        new_version = current_version.bump_alpha()
    elif command == "beta" or command == "b":
        new_version = current_version.bump_beta()
    elif command == "rc":
        new_version = current_version.bump_rc()
    elif command == "post":
        new_version = current_version.bump_post()
    elif command == "release" or command == "finalize":
        new_version = current_version.finalize()
    else:
        print(f"Error: Unknown command '{command}'", file=sys.stderr)
        print(__doc__)
        sys.exit(1)

    new_version_str = str(new_version)

    # Update files
    updated_files = []

    if update_version_in_file(pyproject_path, current_version_str, new_version_str):
        updated_files.append("pyproject.toml")

    init_path = Path("src/orun/__init__.py")
    if update_version_in_file(init_path, current_version_str, new_version_str):
        updated_files.append("src/orun/__init__.py")

    # Print result
    print(f"✓ Version updated: {current_version_str} -> {new_version_str}")
    if updated_files:
        print(f"  Updated files: {', '.join(updated_files)}")


if __name__ == "__main__":
    main()
