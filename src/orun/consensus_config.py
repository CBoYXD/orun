import json
from pathlib import Path
from typing import Dict, List, Optional

from orun.rich_utils import Colors, console


class ConsensusConfig:
    def __init__(self):
        self.config_dir = Path.home() / ".orun"
        self.config_path = self.config_dir / "config.json"
        self.data_dir = Path(__file__).parent.parent.parent / "data" / "consensus"
        self.pipelines: Dict[str, dict] = {}
        self.pipeline_sources: Dict[str, str] = {}  # Track source: 'user' or 'default'

        # Create .orun directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Load configurations (order matters: user first, then defaults)
        self.load_config()
        self.load_default_pipelines()

    def load_config(self):
        """Load consensus pipelines from user config."""
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    consensus_config = config.get("consensus", {})
                    user_pipelines = consensus_config.get("pipelines", {})

                    # Load user-defined pipelines
                    for name, pipeline in user_pipelines.items():
                        self.pipelines[name] = pipeline
                        self.pipeline_sources[name] = "user"
            else:
                # Create default config with consensus section
                self.create_default_config()
        except Exception as e:
            console.print(
                f"Warning: Could not load consensus config: {e}", style=Colors.YELLOW
            )

    def load_default_pipelines(self):
        """Load default consensus pipelines from data/consensus/*.json"""
        try:
            if not self.data_dir.exists():
                # data/consensus/ doesn't exist yet, skip
                return

            # Load all JSON files from data/consensus/
            for json_file in self.data_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        pipeline = json.load(f)
                        pipeline_name = json_file.stem  # filename without .json

                        # Don't overwrite user-defined pipelines
                        if pipeline_name not in self.pipelines:
                            self.pipelines[pipeline_name] = pipeline
                            self.pipeline_sources[pipeline_name] = "default"
                except Exception as e:
                    console.print(
                        f"Warning: Could not load {json_file.name}: {e}",
                        style=Colors.YELLOW,
                    )
        except Exception as e:
            console.print(
                f"Warning: Could not load default pipelines: {e}", style=Colors.YELLOW
            )

    def create_default_config(self):
        """Add consensus section to config if it doesn't exist."""
        try:
            config = {}
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

            # Add consensus section if not present
            if "consensus" not in config:
                config["consensus"] = {
                    "pipelines": {},
                    "_comment": "Custom consensus pipelines. Default pipelines are loaded from data/consensus/",
                }

                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)
        except Exception as e:
            console.print(f"Error creating consensus config: {e}", style=Colors.RED)

    def get_pipeline(self, name: str) -> Optional[dict]:
        """Get a consensus pipeline by name."""
        return self.pipelines.get(name)

    def list_pipelines(self) -> List[Dict[str, str]]:
        """List all available consensus pipelines with descriptions."""
        result = []
        for name, pipeline in self.pipelines.items():
            result.append(
                {
                    "name": name,
                    "description": pipeline.get("description", "No description"),
                    "type": pipeline.get("type", "unknown"),
                    "models_count": len(pipeline.get("models", [])),
                    "source": self.pipeline_sources.get(name, "unknown"),
                }
            )
        return sorted(result, key=lambda x: x["name"])

    def validate_pipeline(
        self, pipeline: dict, available_models: Dict[str, str]
    ) -> tuple[bool, str]:
        """
        Validate a consensus pipeline configuration.
        Returns (is_valid, error_message)
        """
        # Check required fields
        if "type" not in pipeline:
            return False, "Pipeline missing 'type' field"

        if pipeline["type"] not in ["sequential", "parallel"]:
            return False, f"Invalid pipeline type: {pipeline['type']}"

        if "models" not in pipeline or not pipeline["models"]:
            return False, "Pipeline missing 'models' field or it's empty"

        # Validate each model
        model_values = set(available_models.values())  # full names
        for idx, model_config in enumerate(pipeline["models"]):
            if "name" not in model_config:
                return False, f"Model {idx + 1} missing 'name' field"

            model_name = model_config["name"]
            if model_name not in model_values:
                available = ", ".join(sorted(model_values)[:5])
                return False, (
                    f"Model '{model_name}' not found in Ollama.\n"
                    f"Available models: {available}...\n"
                    f"Run 'orun refresh' to sync models."
                )

        # Validate parallel-specific fields
        if pipeline["type"] == "parallel":
            if "aggregation" in pipeline:
                agg = pipeline["aggregation"]
                method = agg.get("method", "synthesis")

                if method == "synthesis":
                    if "synthesizer_model" not in agg:
                        return (
                            False,
                            "Parallel pipeline with synthesis requires 'synthesizer_model'",
                        )

                    synth_model = agg["synthesizer_model"]
                    if synth_model not in model_values:
                        return (
                            False,
                            f"Synthesizer model '{synth_model}' not found in Ollama",
                        )

        return True, ""

    def save_pipeline(self, name: str, pipeline: dict) -> bool:
        """Save a custom pipeline to user config."""
        try:
            config = {}
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

            if "consensus" not in config:
                config["consensus"] = {"pipelines": {}}

            config["consensus"]["pipelines"][name] = pipeline

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            # Update in-memory pipelines
            self.pipelines[name] = pipeline
            self.pipeline_sources[name] = "user"

            return True
        except Exception as e:
            console.print(f"Error saving pipeline '{name}': {e}", style=Colors.RED)
            return False


# Global instance
consensus_config = ConsensusConfig()
