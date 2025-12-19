set shell := ["powershell.exe", "-c"]

# Helper function for version bump and publish
_publish type message:
    python scripts/version_manager.py {{type}}
    uv sync
    uv build
    uv publish
    if (Test-Path dist) { Remove-Item -Recurse -Force dist }
    git add .
    python scripts/git_commit_release.py "{{message}}"
    git push origin -f

# Release a new patch version (1.2.3 -> 1.2.4)
publish message:
    just _publish patch "{{message}}"

# Release a new minor version (1.2.3 -> 1.3.0)
publish-minor message:
    just _publish minor "{{message}}"

# Release a new major version (1.2.3 -> 2.0.0)
publish-major message:
    just _publish major "{{message}}"

# Release an alpha version (1.2.3 -> 1.2.4a1 or 1.2.3a1 -> 1.2.3a2)
publish-alpha message:
    just _publish alpha "{{message}}"

# Release a beta version (1.2.3 -> 1.2.4b1 or 1.2.3b1 -> 1.2.3b2)
publish-beta message:
    just _publish beta "{{message}}"

# Release a release candidate (1.2.3 -> 1.2.4rc1 or 1.2.3rc1 -> 1.2.3rc2)
publish-rc message:
    just _publish rc "{{message}}"

# Release a post version (1.2.3 -> 1.2.3.post1)
publish-post message:
    just _publish post "{{message}}"

# Finalize pre-release (1.2.3a1 -> 1.2.3)
publish-release message:
    just _publish release "{{message}}"

# Set specific version and publish
publish-set version message:
    python scripts/version_manager.py set {{version}}
    uv sync
    uv build
    uv publish
    if (Test-Path dist) { Remove-Item -Recurse -Force dist }
    git add .
    python scripts/git_commit_release.py "{{message}}"
    git push origin -f

# Bump version without publishing (for testing)
bump type:
    python scripts/version_manager.py {{type}}
