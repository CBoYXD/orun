set shell := ["powershell.exe", "-c"]

# Release a new version (bump -> sync -> build -> publish -> commit)
publish message:
    python scripts/bump_version.py
    uv sync
    uv build
    uv publish
    git add .
    python scripts/git_commit_release.py "{{message}}"
    git push origin -f
    @echo "Done! Run 'git push' to push changes."
