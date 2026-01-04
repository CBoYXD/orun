import time
from contextlib import nullcontext
from unittest import TestCase, mock

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
