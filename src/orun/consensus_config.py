import json
from pathlib import Path
from typing import Dict, List, Optional

from orun.rich_utils import Colors, console


def _candidate_data_dirs() -> list[Path]:
    """Return possible locations for packaged or local consensus data."""
    candidates: list[Path] = []

    # Packaged data (when distributed via wheel)
    candidates.append(Path(__file__).resolve().parent / "data")

    # Repo-root data (local dev layout: repo/data next to src/)
    candidates.append(Path(__file__).resolve().parents[2] / "data")

    # Current working directory (fallback)
    candidates.append(Path.cwd() / "data")

    return candidates


def _resolve_consensus_dir() -> Path:
    """Find the first existing directory for consensus data."""
    for base in _candidate_data_dirs():
        candidate = base / "consensus"
        if candidate.exists():
            return candidate
    # Default to repo-style path even if missing
    return Path("data") / "consensus"


class ConsensusConfig:
    def __init__(self):
        self.config_dir = Path.home() / ".orun"
        self.config_path = self.config_dir / "config.json"
        self.user_consensus_dir = self.config_dir / "data" / "consensus"
        self.default_consensus_dir = _resolve_consensus_dir()
        self.pipelines: Dict[str, dict] = {}
        self.pipeline_sources: Dict[str, str] = {}  # Track source: 'user', 'default', or 'config'

        # Create user consensus directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.user_consensus_dir.mkdir(parents=True, exist_ok=True)

        # Load configurations (order matters: default first, then user, then config.json)
        self.load_default_pipelines()
        self.load_user_pipelines()
        self.load_config_pipelines()

    def load_default_pipelines(self):
        """Load default consensus pipelines from packaged/repo data/consensus/*.json"""
        try:
            if not self.default_consensus_dir.exists():
                return

            # Load all JSON files from default consensus directory
            for json_file in self.default_consensus_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        pipeline = json.load(f)
                        pipeline_name = json_file.stem  # filename without .json
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

    def load_user_pipelines(self):
        """Load user custom consensus pipelines from ~/.orun/data/consensus/*.json"""
        try:
            if not self.user_consensus_dir.exists():
                return

            # Load all JSON files from user consensus directory
            for json_file in self.user_consensus_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        pipeline = json.load(f)
                        pipeline_name = json_file.stem  # filename without .json
                        # User pipelines override default ones
                        self.pipelines[pipeline_name] = pipeline
                        self.pipeline_sources[pipeline_name] = "user"
                except Exception as e:
                    console.print(
                        f"Warning: Could not load {json_file.name}: {e}",
                        style=Colors.YELLOW,
                    )
        except Exception as e:
            console.print(
                f"Warning: Could not load user pipelines: {e}", style=Colors.YELLOW
            )

    def load_config_pipelines(self):
        """Load consensus pipelines from config.json (legacy support)."""
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    consensus_config = config.get("consensus", {})
                    config_pipelines = consensus_config.get("pipelines", {})

                    # Load config-defined pipelines (override user and default)
                    for name, pipeline in config_pipelines.items():
                        self.pipelines[name] = pipeline
                        self.pipeline_sources[name] = "config"
        except Exception as e:
            console.print(
                f"Warning: Could not load config pipelines: {e}", style=Colors.YELLOW
            )


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
        """Save a custom pipeline to ~/.orun/data/consensus/{name}.json"""
        try:
            # Ensure user consensus directory exists
            self.user_consensus_dir.mkdir(parents=True, exist_ok=True)

            # Save pipeline to individual JSON file
            pipeline_path = self.user_consensus_dir / f"{name}.json"
            with open(pipeline_path, "w", encoding="utf-8") as f:
                json.dump(pipeline, f, indent=2)

            # Update in-memory pipelines
            self.pipelines[name] = pipeline
            self.pipeline_sources[name] = "user"

            console.print(
                f"Pipeline '{name}' saved to {pipeline_path}", style=Colors.GREEN
            )
            return True
        except Exception as e:
            console.print(f"Error saving pipeline '{name}': {e}", style=Colors.RED)
            return False


# Global instance
consensus_config = ConsensusConfig()
