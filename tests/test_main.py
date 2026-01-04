import sys

from orun import main, utils
from orun.models_config import models_config


def _common_patches(monkeypatch):
    monkeypatch.setattr(utils, "setup_console", lambda: None)
    monkeypatch.setattr(utils, "ensure_orun_config", lambda: {})
    monkeypatch.setattr(utils, "ensure_ollama_running", lambda: None)
    monkeypatch.setattr(utils, "ensure_function_gemma_available", lambda auto_download=True: True)
    monkeypatch.setattr(main.db, "initialize", lambda: None)
    monkeypatch.setattr(models_config, "get_models", lambda: {"alias": "mapped-model"})


def test_main_routes_to_subcommand(monkeypatch):
    _common_patches(monkeypatch)
    called = {}

    def fake_dispatch(args, models):
        called["command"] = args.command
        called["models"] = models

    monkeypatch.setattr(main, "dispatch_command", fake_dispatch)
    monkeypatch.setattr(sys, "argv", ["orun", "models"])

    main.main()

    assert called["command"] == "models"
    assert called["models"] == {"alias": "mapped-model"}


def test_main_routes_to_single_shot(monkeypatch):
    _common_patches(monkeypatch)
    called = {}

    def fake_dispatch(args, models, parser):
        called["prompt"] = args.prompt
        called["model"] = args.model
        called["models"] = models
        called["parser_prog"] = parser.prog

    monkeypatch.setattr(main, "dispatch_single_shot", fake_dispatch)
    monkeypatch.setattr(sys, "argv", ["orun", "hello", "-m", "alias"])

    main.main()

    assert called["prompt"] == ["hello"]
    assert called["model"] == "alias"
    assert called["models"] == {"alias": "mapped-model"}
    assert called["parser_prog"] == "orun"
