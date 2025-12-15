import json
import re
from pathlib import Path
from .utils import colored, Colors
from pynput import keyboard

class YoloMode:
    def __init__(self):
        self.yolo_active = False
        self.config_dir = Path.home() / ".orun"
        self.config_path = self.config_dir / "config.json"
        self.forbidden_commands = []
        self.whitelisted_commands = []
        self.listener = None

        # Create .orun directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Create default config if it doesn't exist
        if not self.config_path.exists():
            self.create_default_config()

        self.load_config()

    def start_hotkey_listener(self):
        """Start global hotkey listener for Ctrl+Y."""
        if self.listener is not None:
            return

        try:
            def on_press(key):
                # Check for Ctrl+Y
                try:
                    # Check if Ctrl is pressed and Y is pressed
                    if key == keyboard.KeyCode.from_char('y') and keyboard.Key.ctrl in keyboard.Controller().pressed_keys:
                        self.toggle(show_message=True)
                except:
                    # Alternative check method
                    if hasattr(key, 'char') and key.char == 'y':
                        self.toggle(show_message=True)

            # Start listener in a separate thread
            self.listener = keyboard.Listener(on_press=on_press)
            self.listener.daemon = True
            self.listener.start()
        except Exception as e:
            # Fail silently if hotkey doesn't work
            print(colored(f"Could not start hotkey listener: {e}", Colors.YELLOW))

    def stop_hotkey_listener(self):
        """Stop the hotkey listener."""
        if self.listener is not None:
            try:
                self.listener.stop()
                self.listener = None
            except:
                pass

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
                    "pip uninstall"
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
                    "help"
                ]
            }
        }

        try:
            with open(self.config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
        except Exception as e:
            print(colored(f"Error creating config: {e}", Colors.RED))

    def load_config(self):
        """Load forbidden and whitelisted commands from JSON config."""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    yolo_config = config.get('yolo', {})
                    self.forbidden_commands = yolo_config.get('forbidden_commands', [])
                    self.whitelisted_commands = yolo_config.get('whitelisted_commands', [])
        except Exception as e:
            print(colored(f"Warning: Could not load config: {e}", Colors.YELLOW))

    def toggle(self, show_message=True):
        """Toggle YOLO mode on/off."""
        self.yolo_active = not self.yolo_active
        status = "ENABLED" if self.yolo_active else "DISABLED"
        mode_color = Colors.RED if self.yolo_active else Colors.GREEN

        if show_message:
            print()
            print(colored(f"🔥 YOLO MODE {status}", mode_color))
            if self.yolo_active:
                print(colored("⚠️  All commands will execute without confirmation!", Colors.YELLOW))
                print(colored("   (Forbidden commands will still be blocked)", Colors.GREY))
                print(colored(f"   Config: {self.config_path}", Colors.GREY))
            else:
                print(colored("✅ Back to normal confirmation mode", Colors.GREEN))
            print()

    def reload_config(self):
        """Reload configuration from file."""
        self.load_config()
        print(colored(f"✅ Config reloaded from {self.config_path}", Colors.GREEN))

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
            r'rm\s+(-rf|--recursive)?\s+/',
            r'chmod\s+[0-9]{3,4}\s+/',
            r'chown\s+.*\s+/',
            r'dd\s+if=.*\s+of=.',
            r':\(\)\s*\{\s*:\|:&\s*\}\s*;',
            r'sudo\s+.*\s+(rm|chmod|chown|dd)',
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
        if not self.yolo_active:
            return False, ""

        # Check if command is forbidden
        allowed, reason = self.is_command_allowed(command)
        if not allowed:
            return False, f"❌ BLOCKED: {reason}"

        # If YOLO mode is active, skip confirmation for allowed commands
        return True, "🔥 YOLO MODE: Executing without confirmation"

# Global instance
yolo_mode = YoloMode()