# Release Scripts

This directory contains scripts for managing orun-py releases.

## Scripts

### version_manager.py

Main version management tool supporting PEP 440 versioning.

**Usage:**
```bash
# Bump versions
python scripts/version_manager.py patch    # 1.2.3 -> 1.2.4
python scripts/version_manager.py minor    # 1.2.3 -> 1.3.0
python scripts/version_manager.py major    # 1.2.3 -> 2.0.0

# Pre-releases
python scripts/version_manager.py alpha    # 1.2.3 -> 1.2.4a1 or 1.2.3a1 -> 1.2.3a2
python scripts/version_manager.py beta     # 1.2.3 -> 1.2.4b1 or 1.2.3b1 -> 1.2.3b2
python scripts/version_manager.py rc       # 1.2.3 -> 1.2.4rc1 or 1.2.3rc1 -> 1.2.3rc2

# Post releases and finalization
python scripts/version_manager.py post     # 1.2.3 -> 1.2.3.post1
python scripts/version_manager.py release  # 1.2.3a1 -> 1.2.3

# Set specific version
python scripts/version_manager.py set 2.0.0
```

Updates both `pyproject.toml` and `src/orun/__init__.py`.

### git_commit_release.py

Creates a git commit with the current version from `pyproject.toml`.

**Usage:**
```bash
python scripts/git_commit_release.py "Your change description"
```

Generates commit message: `Update to X.Y.Z. Changes: Your change description`

### bump_version.py (Legacy)

Legacy version bumper. Use `version_manager.py` instead for full PEP 440 support.

## Quick Release with Just

The easiest way to release is using just commands (see justfile):

```bash
# Standard releases
just publish "Fix consensus loading"
just publish-minor "Add new feature"
just publish-major "Breaking changes"

# Pre-releases
just publish-alpha "Test new consensus system"
just publish-beta "Beta testing"
just publish-rc "Release candidate 1"

# Other
just publish-post "Hotfix for critical bug"
just publish-release "Finalize 2.0.0"
just publish-set 2.0.0 "Major rewrite"
```

These commands automatically:
1. Bump version
2. Sync dependencies
3. Build package
4. Publish to PyPI
5. Clean dist/ directory
6. Git commit
7. Git push
