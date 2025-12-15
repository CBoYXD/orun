set shell := ["powershell.exe", "-c"]

# Release a new version (bump -> sync -> build -> publish -> commit)
publish message:
    python scripts/bump_version.py
    uv sync
    uv build
    uv publish
    if (Test-Path dist) { Remove-Item -Recurse -Force dist }
    git add .
    python scripts/git_commit_release.py "{{message}}"
    git push origin -f
    uv build
    uv pip install .
    uv tool install . --force
    @echo "Upgraded locally and globally!"
    @echo "Done!"
