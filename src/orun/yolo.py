import json
import re
from pathlib import Path

from orun.rich_utils import Colors, console


class YoloMode:
    def __init__(self):
        self.yolo_active = False
        self.config_dir = Path.home() / ".orun"
        self.config_path = self.config_dir / "config.json"
        self.forbidden_commands = []
        self.whitelisted_commands = []
        # self.listener = None # Removed pynput listener

        # Create .orun directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Create default config if it doesn't exist
        if not self.config_path.exists():
            self.create_default_config()

        self.load_config()

    # Removed start_hotkey_listener and stop_hotkey_listener methods

    def create_default_config(self):
        """Create a default configuration file."""
        default_config = {
            "yolo": {
                "forbidden_commands": [
                    "rm -rf",
                    "format",
                    "fdisk",
                    "mkfs",
                    "shutdown",
                    "reboot",
                    "halt",
                    "poweroff",
                    ":(){ :|:& };:",
                    "sudo rm",
                    "chmod 777",
                    "chown root",
                    "dd if=",
                    "mv /*",
                    "cp /*",
                    "curl -X DELETE",
                    "wget -O /dev/null",
                    "> /dev/sda",
                    "pip uninstall",
                ],
                "whitelisted_commands": [
                    "ls",
                    "pwd",
                    "cd",
                    "cat",
                    "head",
                    "tail",
                    "grep",
                    "find",
                    "git status",
                    "git log",
                    "git diff",
                    "git show",
                    "git branch",
                    "git checkout",
                    "git add",
                    "git commit",
                    "git push",
                    "git pull",
                    "python",
                    "python3",
                    "pip",
                    "pip3",
                    "npm",
                    "node",
                    "yarn",
                    "pnpm",
                    "cargo",
                    "rustc",
                    "go",
                    "docker ps",
                    "docker images",
                    "docker logs",
                    "docker inspect",
                    "docker build",
                    "docker run",
                    "docker-compose",
                    "docker compose",
                    "kubectl",
                    "helm",
                    "make",
                    "cmake",
                    "gcc",
                    "g++",
                    "clang",
                    "clang++",
                    "javac",
                    "java",
                    "mvn",
                    "gradle",
                    "pytest",
                    "coverage",
                    "black",
                    "flake8",
                    "mypy",
                    "eslint",
                    "prettier",
                    "echo",
                    "which",
                    "whereis",
                    "type",
                    "man",
                    "tldr",
                    "help",
                ],
            }
        }

        try:
            with open(self.config_path, "w") as f:
                json.dump(default_config, f, indent=2)
        except Exception as e:
            console.print(f"Error creating config: {e}", style=Colors.RED)

    def load_config(self):
        """Load forbidden and whitelisted commands from JSON config."""
        try:
            if self.config_path.exists():
                with open(self.config_path, "r") as f:
                    config = json.load(f)
                    yolo_config = config.get("yolo", {})
                    self.forbidden_commands = yolo_config.get("forbidden_commands", [])
                    self.whitelisted_commands = yolo_config.get(
                        "whitelisted_commands", []
                    )
        except Exception as e:
            console.print(f"Warning: Could not load config: {e}", style=Colors.YELLOW)

    def toggle(self, show_message=True):
        """Toggle YOLO mode on/off."""
        self.yolo_active = not self.yolo_active
        status = "ENABLED" if self.yolo_active else "DISABLED"
        mode_color = Colors.RED if self.yolo_active else Colors.GREEN

        if show_message:
            console.print()
            console.print(f"🔥 YOLO MODE {status}", style=mode_color)
            if self.yolo_active:
                console.print(
                    "⚠️  All commands will execute without confirmation!",
                    style=Colors.YELLOW,
                )
                console.print(
                    "   (Forbidden commands will still be blocked)", style=Colors.GREY
                )
                console.print(f"   Config: {self.config_path}", style=Colors.GREY)
            else:
                console.print("✅ Back to normal confirmation mode", style=Colors.GREEN)
            console.print()

    def reload_config(self):
        """Reload configuration from file."""
        self.load_config()
        console.print(f"✅ Config reloaded from {self.config_path}", style=Colors.GREEN)

    def is_command_allowed(self, command: str) -> tuple[bool, str]:
        """
        Check if a command is allowed to run.
        Returns (allowed, reason)
        """
        command_lower = command.lower().strip()

        # Check if command matches any forbidden patterns
        for forbidden in self.forbidden_commands:
            if forbidden.lower() in command_lower:
                return False, f"Command contains forbidden pattern: '{forbidden}'"

        # Check for potentially dangerous patterns not in the list
        dangerous_patterns = [
            r"rm\s+(-rf|--recursive)?\s+/",
            r"chmod\s+[0-9]{3,4}\s+/",
            r"chown\s+.*\s+/",
            r"dd\s+if=.*\s+of=.",
            r":\(\)\s*\{\s*:\|:&\s*\}\s*;",
            r"sudo\s+.*\s+(rm|chmod|chown|dd)",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, command_lower):
                return False, "Potentially dangerous command detected"

        return True, ""

    def is_command_whitelisted(self, command: str) -> bool:
        """Check if a command is in the whitelist."""
        command_parts = command.strip().split()
        if not command_parts:
            return False

        base_command = command_parts[0]

        # Check exact match
        if base_command in self.whitelisted_commands:
            return True

        # Check for multi-command whitelist (e.g., "git status")
        for whitelisted in self.whitelisted_commands:
            whitelisted_parts = whitelisted.split()
            if len(whitelisted_parts) > 1 and command.startswith(whitelisted.lower()):
                return True

        return False

    def should_skip_confirmation(self, command: str) -> tuple[bool, str]:
        """
        Determine if confirmation should be skipped.
        Returns (skip, reason)
        """
        # If command is whitelisted, always skip confirmation
        if self.is_command_whitelisted(command):
            return True, "✅ WHITELISTED: Executing without confirmation"

        # If YOLO mode is active, skip confirmation for allowed commands
        if self.yolo_active:
            # Check if command is forbidden
            allowed, reason = self.is_command_allowed(command)
            if not allowed:
                return False, f"❌ BLOCKED: {reason}"
            return True, "🔥 YOLO MODE: Executing without confirmation"

        return False, ""


# Global instance
yolo_mode = YoloMode()
