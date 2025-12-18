import json
from pathlib import Path
from typing import Dict, Optional

import ollama

from orun.rich_utils import console
from orun.utils import Colors, print_error, print_success


class ModelsConfig:
    def __init__(self):
        self.config_dir = Path.home() / ".orun"
        self.config_path = self.config_dir / "config.json"
        self.models: Dict[str, str] = {}  # alias -> full_name
        self.active_model: Optional[str] = None

        # Create .orun directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Load configuration
        self.load_config()

    def load_config(self):
        """Load models configuration from config.json."""
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.models = config.get("models", {})
                    self.active_model = config.get("active_model")
            else:
                # Create default config
                self.create_default_config()
        except Exception as e:
            console.print(
                f"Warning: Could not load models config: {e}",
                style=Colors.YELLOW
            )
            self.models = {}
            self.active_model = None

    def create_default_config(self):
        """Create default config.json with models section."""
        try:
            config = {}
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

            # Add models section if not present
            if "models" not in config:
                config["models"] = {}
            if "active_model" not in config:
                config["active_model"] = None

            self.save_config(config)
        except Exception as e:
            console.print(
                f"Error creating models config: {e}",
                style=Colors.RED
            )

    def save_config(self, config: dict = None):
        """Save models configuration to config.json."""
        try:
            # Load existing config or use provided one
            if config is None:
                if self.config_path.exists():
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                else:
                    config = {}

            # Update models and active_model
            config["models"] = self.models
            config["active_model"] = self.active_model

            # Save to file
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            return True
        except Exception as e:
            console.print(
                f"Error saving models config: {e}",
                style=Colors.RED
            )
            return False

    def refresh_ollama_models(self):
        """Sync models from Ollama API."""
        try:
            # Get list of models from Ollama
            response = ollama.list()

            # Handle both dict and object responses
            if hasattr(response, 'models'):
                ollama_models = response.models
            elif isinstance(response, dict):
                ollama_models = response.get("models", [])
            else:
                ollama_models = []

            if not ollama_models:
                console.print("No models found in Ollama.", style=Colors.YELLOW)
                return

            # Build new models dict preserving existing shortcuts
            new_models = {}
            existing_aliases = {v: k for k, v in self.models.items()}  # full_name -> alias

            for model_info in ollama_models:
                # Handle both dict and object model info
                if hasattr(model_info, 'model'):
                    full_name = model_info.model
                elif hasattr(model_info, 'name'):
                    full_name = model_info.name
                elif isinstance(model_info, dict):
                    full_name = model_info.get("model", model_info.get("name", ""))
                else:
                    full_name = ""
                if not full_name:
                    continue

                # Check if we already have an alias for this model
                if full_name in existing_aliases:
                    alias = existing_aliases[full_name]
                else:
                    # Create default alias from model name
                    # e.g., "llama3.1:8b" -> "llama"
                    alias = full_name.split(":")[0].split("-")[0]

                    # Ensure alias is unique
                    original_alias = alias
                    counter = 1
                    while alias in new_models:
                        alias = f"{original_alias}{counter}"
                        counter += 1

                new_models[alias] = full_name

            # Update models
            old_models = self.models.copy()
            self.models = new_models

            # If active model no longer exists, clear it
            if self.active_model and self.active_model not in self.models.values():
                console.print(
                    f"Active model '{self.active_model}' no longer available.",
                    style=Colors.YELLOW
                )
                self.active_model = None

            # Save to config
            self.save_config()

            # Show summary
            added = set(new_models.values()) - set(old_models.values())
            removed = set(old_models.values()) - set(new_models.values())

            if added:
                console.print(f"✅ Added {len(added)} model(s)", style=Colors.GREEN)
            if removed:
                console.print(f"🗑️  Removed {len(removed)} model(s)", style=Colors.YELLOW)

            print_success(f"Synced {len(new_models)} models from Ollama")

        except Exception as e:
            print_error(f"Failed to sync models from Ollama: {e}")

    def get_models(self) -> Dict[str, str]:
        """Get all models (alias -> full_name mapping)."""
        return self.models.copy()

    def get_active_model(self) -> Optional[str]:
        """Get the currently active model (full name)."""
        return self.active_model

    def set_active_model(self, identifier: str) -> bool:
        """
        Set the active model by alias or full name.
        Returns True if successful, False otherwise.
        """
        # Check if identifier is an alias
        if identifier in self.models:
            self.active_model = self.models[identifier]
            self.save_config()
            return True

        # Check if identifier is a full name
        if identifier in self.models.values():
            self.active_model = identifier
            self.save_config()
            return True

        return False

    def update_model_shortcut(self, identifier: str, new_shortcut: str) -> bool:
        """
        Update a model's shortcut (alias).
        identifier: current alias or full model name
        new_shortcut: new alias to assign
        Returns True if successful, False otherwise.
        """
        # Find the model's full name
        full_name = None

        if identifier in self.models:
            # identifier is an existing alias
            full_name = self.models[identifier]
        elif identifier in self.models.values():
            # identifier is a full name
            full_name = identifier

        if not full_name:
            return False

        # Check if new_shortcut is already taken by a different model
        if new_shortcut in self.models and self.models[new_shortcut] != full_name:
            return False

        # Remove old alias(es) for this model
        self.models = {k: v for k, v in self.models.items() if v != full_name}

        # Add new alias
        self.models[new_shortcut] = full_name

        # Save to config
        self.save_config()
        return True

    def resolve_model_name(self, identifier: str) -> Optional[str]:
        """
        Resolve an alias or full name to the full model name.
        Returns None if not found.
        """
        # Check if it's an alias
        if identifier in self.models:
            return self.models[identifier]

        # Check if it's already a full name
        if identifier in self.models.values():
            return identifier

        return None


# Global instance
models_config = ModelsConfig()
