import json
from pathlib import Path

from orun.rich_utils import console

from .utils import Colors


class SearchConfig:
    def __init__(self):
        self.config_dir = Path.home() / ".orun"
        self.config_path = self.config_dir / "config.json"
        self.google_api_key = None
        self.google_cse_id = None

        # Create .orun directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Load or create config
        self.load_config()

    def load_config(self):
        """Load search configuration from JSON config."""
        try:
            if self.config_path.exists():
                with open(self.config_path, "r") as f:
                    config = json.load(f)
                    search_config = config.get("search", {})
                    self.google_api_key = search_config.get("google_api_key")
                    self.google_cse_id = search_config.get("google_cse_id")
            else:
                # Create default config with search section
                self.create_default_search_config()
        except Exception as e:
            console.print(f"Warning: Could not load search config: {e}", style=Colors.YELLOW)

    def create_default_search_config(self):
        """Add search section to config if it doesn't exist."""
        try:
            config = {}
            if self.config_path.exists():
                with open(self.config_path, "r") as f:
                    config = json.load(f)

            # Add search section if not present
            if "search" not in config:
                config["search"] = {
                    "google_api_key": None,
                    "google_cse_id": None,
                    "_comment": "Get Google Custom Search API key from https://developers.google.com/custom-search/v1/overview"
                }

                with open(self.config_path, "w") as f:
                    json.dump(config, f, indent=2)
        except Exception as e:
            console.print(f"Error updating search config: {e}", style=Colors.RED)

    def has_google_credentials(self) -> bool:
        """Check if Google API credentials are configured."""
        return bool(self.google_api_key and self.google_cse_id)

    def save_google_credentials(self, api_key: str, cse_id: str) -> bool:
        """Save Google API credentials to config file."""
        try:
            config = {}
            if self.config_path.exists():
                with open(self.config_path, "r") as f:
                    config = json.load(f)

            # Update search section
            config["search"] = {
                "google_api_key": api_key,
                "google_cse_id": cse_id,
                "_comment": "Google Custom Search API credentials"
            }

            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2)

            # Update instance variables
            self.google_api_key = api_key
            self.google_cse_id = cse_id

            return True
        except Exception as e:
            console.print(f"Error saving search config: {e}", style=Colors.RED)
            return False


# Global instance
search_config = SearchConfig()
