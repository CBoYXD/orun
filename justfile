set shell := ["powershell.exe", "-c"]

# Release with specific part and type (e.g. just publish minor alpha "msg")
publish part type message:
    python scripts/version_manager.py {{part}} {{type}}
    uv sync
    uv build
    uv publish
    if (Test-Path dist) { Remove-Item -Recurse -Force dist }
    git add .
    python scripts/git_commit_release.py "{{message}}"
    git push origin -f
