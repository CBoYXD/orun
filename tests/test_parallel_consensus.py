import time
from contextlib import nullcontext
from unittest import TestCase, mock

import sys
import time
import types
from contextlib import nullcontext
from unittest import TestCase, mock


class _DummyConsole:
    def print(self, *args, **kwargs):
        return None


def _install_stub_modules() -> None:
    """Install lightweight stub modules so consensus imports without heavy deps."""
    if "ollama" not in sys.modules:
        sys.modules["ollama"] = mock.Mock()

    rich_utils = types.ModuleType("orun.rich_utils")
    rich_utils.console = _DummyConsole()

    class Colors:
        RED = "red"
        YELLOW = "yellow"
        GREEN = "green"
        MAGENTA = "magenta"
        CYAN = "cyan"
        GREY = "grey"

    rich_utils.Colors = Colors

    def _print_error(message: str) -> None:
        return None

    rich_utils.print_error = _print_error

    db_module = types.ModuleType("orun.db")

    class _DummyDB:
        def connection_context(self):
            return nullcontext()

    db_module.db = _DummyDB()

    def _add_message(conversation_id: int, role: str, content: str, images=None):
        return None

    db_module.add_message = _add_message
    db_module.create_conversation = lambda model: 1

    tools_module = types.ModuleType("orun.tools")
    tools_module.TOOL_DEFINITIONS = []

    utils_module = types.ModuleType("orun.utils")
    utils_module.ensure_ollama_running = lambda: None

    consensus_config_module = types.ModuleType("orun.consensus_config")
    consensus_config_module.consensus_config = mock.Mock()

    models_config_module = types.ModuleType("orun.models_config")
    models_config_module.models_config = mock.Mock(get_models=lambda: [])

    core_module = types.ModuleType("orun.core")
    core_module.execute_tool_calls = lambda *args, **kwargs: None
    core_module.handle_ollama_stream = lambda *args, **kwargs: ""

    sys.modules["orun.rich_utils"] = rich_utils
    sys.modules["orun.db"] = db_module
    sys.modules["orun.tools"] = tools_module
    sys.modules["orun.utils"] = utils_module
    sys.modules["orun.consensus_config"] = consensus_config_module
    sys.modules["orun.models_config"] = models_config_module
    sys.modules["orun.core"] = core_module


_install_stub_modules()

from orun import consensus


class ParallelConsensusTests(TestCase):
    def test_parallel_execution_and_order_is_deterministic(self) -> None:
        pipeline = {
            "models": [
                {"name": "model_a"},
                {"name": "model_b"},
            ],
            "aggregation": {"method": "best_of"},
        }
        durations = {"model_a": 0.3, "model_b": 0.3}
        start_times: dict[str, float] = {}

        def fake_chat(model: str, messages, tools=None, stream=False, options=None):
            start_times[model] = time.perf_counter()
            time.sleep(durations[model])
            return {"message": {"content": f"output-{model}"}}

        mock_db = mock.Mock()
        mock_db.connection_context.return_value = nullcontext()

        with (
            mock.patch("orun.consensus.ollama.chat", side_effect=fake_chat),
            mock.patch("orun.consensus.db.db", mock_db),
            mock.patch("orun.consensus.db.add_message") as mock_add_message,
            mock.patch("orun.consensus.unload_model"),
            mock.patch("orun.consensus.console.print"),
        ):
            start = time.perf_counter()
            result = consensus.run_parallel_consensus(
                pipeline=pipeline,
                pipeline_name="test",
                user_prompt="hi",
                image_paths=None,
                system_prompt=None,
                tools_enabled=False,
                conversation_id=1,
                model_options=None,
            )
            elapsed = time.perf_counter() - start

        self.assertIn("Response 1 (model_a)", result)
        self.assertIn("Response 2 (model_b)", result)
        self.assertLess(
            result.index("Response 1 (model_a)"), result.index("Response 2 (model_b)")
        )
        self.assertLess(elapsed, sum(durations.values()) * 0.8)
        self.assertEqual(mock_add_message.call_count, 2)

    def test_model_errors_do_not_block_other_results(self) -> None:
        pipeline = {
            "models": [
                {"name": "model_ok"},
                {"name": "model_fail"},
            ],
            "aggregation": {"method": "best_of"},
        }

        def fake_chat(model: str, messages, tools=None, stream=False, options=None):
            if model == "model_fail":
                raise RuntimeError("boom")
            return {"message": {"content": "success"}}

        mock_db = mock.Mock()
        mock_db.connection_context.return_value = nullcontext()

        with (
            mock.patch("orun.consensus.ollama.chat", side_effect=fake_chat),
            mock.patch("orun.consensus.db.db", mock_db),
            mock.patch("orun.consensus.db.add_message") as mock_add_message,
            mock.patch("orun.consensus.unload_model"),
            mock.patch("orun.consensus.console.print"),
            mock.patch("orun.consensus.print_error"),
        ):
            result = consensus.run_parallel_consensus(
                pipeline=pipeline,
                pipeline_name="test",
                user_prompt="hi",
                image_paths=None,
                system_prompt=None,
                tools_enabled=False,
                conversation_id=1,
                model_options=None,
            )

        self.assertIn("Response 1 (model_ok)", result)
        self.assertNotIn("model_fail", result)
        mock_add_message.assert_called_once()
