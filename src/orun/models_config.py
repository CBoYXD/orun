import json
from pathlib import Path
from typing import Dict, List, Optional

import ollama

from orun.rich_utils import console
from orun.utils import Colors, print_error, print_success


class ModelsConfig:
    """
    Manages models configuration in JSON format.

    Structure:
    {
      "models": {
        "gpt-oss:20b": {
          "shortcuts": ["gpt", "gpt-oss"],
          "options": {"temperature": 0.7, ...}
        },
        ...
      },
      "active_model": "gpt-oss:20b"
    }
    """
    def __init__(self):
        self.config_dir = Path.home() / ".orun"
        self.config_path = self.config_dir / "config.json"
        self.models: Dict[str, Dict] = {}  # full_name -> {shortcuts: [...], options: {...}}
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

                    # Load models with new structure
                    raw_models = config.get("models", {})

                    # Handle migration from old format (alias -> name) to new format (name -> {shortcuts, options})
                    if raw_models and isinstance(list(raw_models.values())[0], str):
                        # Old format: migrate
                        self.models = self._migrate_old_format(raw_models)
                    else:
                        # New format
                        self.models = raw_models

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

    def _migrate_old_format(self, old_models: Dict[str, str]) -> Dict[str, Dict]:
        """Migrate from old format (alias -> name) to new format (name -> {shortcuts, options})."""
        new_models = {}
        for alias, full_name in old_models.items():
            if full_name not in new_models:
                new_models[full_name] = {
                    "shortcuts": [alias],
                    "options": {}
                }
            else:
                # Add alias to existing shortcuts
                if alias not in new_models[full_name]["shortcuts"]:
                    new_models[full_name]["shortcuts"].append(alias)

        console.print("Migrated models to new format", style=Colors.GREEN)
        return new_models

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

            # Build new models dict preserving existing shortcuts and options
            new_models = {}

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

                # Check if we already have this model
                if full_name in self.models:
                    # Preserve existing shortcuts and options
                    new_models[full_name] = self.models[full_name]
                else:
                    # Create new entry with default shortcut
                    # e.g., "llama3.1:8b" -> "llama"
                    default_alias = full_name.split(":")[0].split("-")[0]

                    # Ensure alias is unique across all models
                    counter = 1
                    alias = default_alias
                    while self._alias_exists_in_models(alias, new_models):
                        alias = f"{default_alias}{counter}"
                        counter += 1

                    new_models[full_name] = {
                        "shortcuts": [alias],
                        "options": {}
                    }

            # Update models
            old_model_names = set(self.models.keys())
            new_model_names = set(new_models.keys())

            self.models = new_models

            # If active model no longer exists, clear it
            if self.active_model and self.active_model not in self.models:
                console.print(
                    f"Active model '{self.active_model}' no longer available.",
                    style=Colors.YELLOW
                )
                self.active_model = None

            # Save to config
            self.save_config()

            # Show summary
            added = new_model_names - old_model_names
            removed = old_model_names - new_model_names

            if added:
                console.print(f"✅ Added {len(added)} model(s)", style=Colors.GREEN)
            if removed:
                console.print(f"🗑️  Removed {len(removed)} model(s)", style=Colors.YELLOW)

            print_success(f"Synced {len(new_models)} models from Ollama")

        except Exception as e:
            print_error(f"Failed to sync models from Ollama: {e}")

    def _alias_exists_in_models(self, alias: str, models: Dict[str, Dict]) -> bool:
        """Check if an alias already exists in any model's shortcuts."""
        for model_data in models.values():
            if alias in model_data.get("shortcuts", []):
                return True
        return False

    def get_models(self) -> Dict[str, str]:
        """Get all models as alias -> full_name mapping (for backward compatibility)."""
        result = {}
        for full_name, model_data in self.models.items():
            for alias in model_data.get("shortcuts", []):
                result[alias] = full_name
        return result

    def get_models_full(self) -> Dict[str, Dict]:
        """Get full models configuration."""
        return self.models.copy()

    def get_active_model(self) -> Optional[str]:
        """Get the currently active model (full name)."""
        return self.active_model

    def set_active_model(self, identifier: str) -> bool:
        """
        Set the active model by alias or full name.
        Returns True if successful, False otherwise.
        """
        # Resolve identifier to full name
        full_name = self.resolve_model_name(identifier)

        if full_name:
            self.active_model = full_name
            self.save_config()
            return True

        return False

    def update_model_shortcut(self, identifier: str, new_shortcut: str) -> bool:
        """
        Add or update a model's shortcut.
        identifier: current alias or full model name
        new_shortcut: new alias to add/set
        Returns True if successful, False otherwise.
        """
        # Find the model's full name
        full_name = self.resolve_model_name(identifier)

        if not full_name:
            return False

        # Check if new_shortcut is already used by a different model
        for model_name, model_data in self.models.items():
            if model_name != full_name and new_shortcut in model_data.get("shortcuts", []):
                return False

        # Add the new shortcut to this model
        if "shortcuts" not in self.models[full_name]:
            self.models[full_name]["shortcuts"] = []

        if new_shortcut not in self.models[full_name]["shortcuts"]:
            self.models[full_name]["shortcuts"].append(new_shortcut)

        # Save to config
        self.save_config()
        return True

    def remove_model_shortcut(self, identifier: str, shortcut_to_remove: str) -> bool:
        """
        Remove a specific shortcut from a model.
        Returns True if successful, False otherwise.
        """
        full_name = self.resolve_model_name(identifier)

        if not full_name:
            return False

        shortcuts = self.models[full_name].get("shortcuts", [])

        if shortcut_to_remove in shortcuts:
            # Don't allow removing the last shortcut
            if len(shortcuts) <= 1:
                return False

            shortcuts.remove(shortcut_to_remove)
            self.save_config()
            return True

        return False

    def set_model_options(self, identifier: str, options: Dict) -> bool:
        """
        Set options for a model.
        Returns True if successful, False otherwise.
        """
        full_name = self.resolve_model_name(identifier)

        if not full_name:
            return False

        self.models[full_name]["options"] = options
        self.save_config()
        return True

    def get_model_options(self, identifier: str) -> Optional[Dict]:
        """Get options for a model."""
        full_name = self.resolve_model_name(identifier)

        if full_name and full_name in self.models:
            return self.models[full_name].get("options", {})

        return None

    def resolve_model_name(self, identifier: str) -> Optional[str]:
        """
        Resolve an alias or full name to the full model name.
        Returns None if not found.
        """
        # Check if it's already a full name
        if identifier in self.models:
            return identifier

        # Check if it's an alias in any model's shortcuts
        for full_name, model_data in self.models.items():
            if identifier in model_data.get("shortcuts", []):
                return full_name

        return None


# Global instance
models_config = ModelsConfig()
