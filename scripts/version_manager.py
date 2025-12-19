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
        v = Version(f"{self.major + 1}.0.0")
        v.pre_type = None
        v.pre_number = None
        v.post = None
        return v

    def bump_minor(self):
        """Bump minor version: 1.2.3 -> 1.3.0"""
        v = Version(f"{self.major}.{self.minor + 1}.0")
        v.pre_type = None
        v.pre_number = None
        v.post = None
        return v

    def bump_patch(self):
        """Bump patch version: 1.2.3 -> 1.2.4"""
        v = Version(f"{self.major}.{self.minor}.{self.patch + 1}")
        v.pre_type = None
        v.pre_number = None
        v.post = None
        return v

    def bump_with_stage(self, part, stage):
        """Bump version part and apply stage."""
        # 1. Determine base version based on part
        if part == 'major':
            base = self.bump_major()
        elif part == 'minor':
            base = self.bump_minor()
        elif part == 'patch':
            base = self.bump_patch()
        elif part == 'current':
            base = Version(str(self))
        else:
            raise ValueError(f"Unknown part: {part}")

        # 2. Apply stage
        if not stage or stage in ['stable', 'release']:
            # Strip pre/post if explicitly stable or just base bump
            if stage:
                base.pre_type = None
                base.pre_number = None
                base.post = None
            return base

        if stage in ['alpha', 'a', 'beta', 'b', 'rc']:
            # Normalize type
            t = 'a' if stage in ['alpha', 'a'] else 'b' if stage in ['beta', 'b'] else 'rc'
            
            # If numbers match original and type matches, increment
            numbers_match = (base.major == self.major and 
                             base.minor == self.minor and 
                             base.patch == self.patch)
            
            if numbers_match and self.pre_type == t:
                base.pre_type = t
                base.pre_number = self.pre_number + 1
            else:
                base.pre_type = t
                base.pre_number = 1
            base.post = None
            return base
            
        if stage == 'post':
            numbers_match = (base.major == self.major and 
                             base.minor == self.minor and 
                             base.patch == self.patch)
            
            if numbers_match and self.post is not None:
                base.post = self.post + 1
            else:
                base.post = 1
            return base

        return base

    def bump_alpha(self):
        """Legacy bump alpha."""
        if self.pre_type == 'a':
            return self.bump_with_stage('current', 'alpha')
        return self.bump_with_stage('patch', 'alpha')

    def bump_beta(self):
        """Legacy bump beta."""
        if self.pre_type == 'b':
            return self.bump_with_stage('current', 'beta')
        return self.bump_with_stage('patch', 'beta')

    def bump_rc(self):
        """Legacy bump rc."""
        if self.pre_type == 'rc':
            return self.bump_with_stage('current', 'rc')
        return self.bump_with_stage('patch', 'rc')

    def bump_post(self):
        """Legacy bump post."""
        return self.bump_with_stage('current', 'post')

    def finalize(self):
        """Finalize pre-release."""
        return self.bump_with_stage('current', 'stable')

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

    args = sys.argv[1:]
    command = args[0].lower()
    
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
        if len(args) < 2:
            print("Error: 'set' requires a version argument", file=sys.stderr)
            sys.exit(1)
        try:
            new_version = Version(args[1])
        except ValueError as e:
            print(f"Error: Invalid version format: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Check for <part> <stage> format (e.g. "minor alpha", "patch stable")
    elif command in ['major', 'minor', 'patch', 'current']:
        stage = args[1].lower() if len(args) > 1 else None
        # If no stage provided for major/minor/patch, default to stable bump (standard behavior)
        if not stage and command != 'current':
            stage = 'stable'
        
        new_version = current_version.bump_with_stage(command, stage)

    # Legacy/Shortcut commands
    elif command in ["alpha", "a"]:
        new_version = current_version.bump_alpha()
    elif command in ["beta", "b"]:
        new_version = current_version.bump_beta()
    elif command in ["rc"]:
        new_version = current_version.bump_rc()
    elif command in ["post"]:
        new_version = current_version.bump_post()
    elif command in ["release", "finalize"]:
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
    print(f"Version updated: {current_version_str} -> {new_version_str}")
    if updated_files:
        print(f"Updated files: {', '.join(updated_files)}")


if __name__ == "__main__":
    main()
