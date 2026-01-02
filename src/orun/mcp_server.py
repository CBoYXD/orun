import asyncio
import json
from typing import Any

from orun import core
from orun.models_config import models_config
from orun.rich_utils import Colors, console, print_error, print_success


class MissingDependencyError(Exception):
    """Raised when optional dependencies for the MCP server are missing."""


class ServerStartupError(Exception):
    """Raised when the MCP server cannot be started."""


def _load_robyn():
    try:
        from robyn import Robyn, jsonify
    except Exception as exc:  # ImportError or other runtime errors
        raise MissingDependencyError(
            "Robyn is not installed. Install optional dependency with: pip install \"orun-py[mcp]\""
        ) from exc
    return Robyn, jsonify


def _parse_json_body(raw_body: Any) -> dict:
    if raw_body is None:
        return {}

    if isinstance(raw_body, (bytes, bytearray)):
        raw_body = raw_body.decode("utf-8", errors="ignore")

    if isinstance(raw_body, str):
        raw_body = raw_body.strip()
        if not raw_body:
            return {}
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON body: {exc}") from exc

    if isinstance(raw_body, dict):
        return raw_body

    try:
        return dict(raw_body)
    except Exception:
        raise ValueError("Unsupported request body format")


def start_mcp_server(host: str, port: int, model_alias: str | None = None, allow_tools: bool = True) -> None:
    """
    Start a lightweight Robyn-based server that forwards requests to orun.

    The server exposes:
      - GET  /health  -> {"status": "ok"}
      - POST /chat    -> {"response": "<model output>"}

    Parameters
    ----------
    host: str
        Host interface to bind (default: 127.0.0.1)
    port: int
        TCP port to bind (default: 8000)
    model_alias: str | None
        Optional model alias/name to force for the server. Falls back to active model.
    allow_tools: bool
        Whether to allow agent tools during server calls.
    """
    Robyn, jsonify = _load_robyn()

    app = Robyn(__file__)
    model_name = None

    if model_alias:
        model_name = models_config.resolve_model_name(model_alias)
    if not model_name:
        model_name = models_config.get_active_model()

    if not model_name:
        raise ServerStartupError(
            "No model configured. Set an active model with `orun set-active <model>` or pass --model."
        )

    console.print(
        f"🚀 Starting Robyn MCP server on [bold]{host}:{port}[/bold] using model [green]{model_name}[/green]",
        style=Colors.CYAN,
    )
    if not allow_tools:
        console.print("⚠️ Tools are disabled for server requests.", style=Colors.YELLOW)

    @app.get("/health")
    async def health(request):
        return jsonify({"status": "ok"})

    @app.post("/chat")
    async def chat(request):
        try:
            payload = _parse_json_body(getattr(request, "body", None))
        except ValueError as exc:
            return jsonify({"error": str(exc)}, status_code=400)

        prompt = payload.get("prompt")
        if not prompt:
            return jsonify({"error": "Missing 'prompt' field"}, status_code=400)

        options = payload.get("options")
        system_prompt = payload.get("system_prompt") or payload.get("system")
        yolo_mode = bool(payload.get("yolo"))
        use_tools = allow_tools and payload.get("use_tools", True)

        try:
            result = await asyncio.to_thread(
                core.run_single_shot,
                model_name,
                prompt,
                payload.get("images"),
                use_tools=use_tools,
                yolo=yolo_mode,
                prompt_template=payload.get("prompt_templates") or payload.get("prompt_template"),
                strategy_template=payload.get("strategy_template"),
                file_paths=payload.get("files"),
                stdin_content=payload.get("stdin"),
                system_prompt=system_prompt,
                dir_context=payload.get("dir_context"),
                clipboard_content=payload.get("clipboard"),
                model_options=options,
                quiet=True,
            )
        except Exception as exc:
            print_error(f"MCP server chat error: {exc}")
            return jsonify({"error": str(exc)}, status_code=500)

        if not result:
            return jsonify({"error": "Model returned empty response"}, status_code=502)

        return jsonify({"response": result})

    try:
        app.start(host=host, port=port)
    except TypeError:
        # Older Robyn versions use 'url' instead of 'host'
        app.start(port=port, url=host)
    except Exception as exc:
        raise ServerStartupError(f"Failed to start MCP server: {exc}") from exc
    else:
        print_success("Robyn MCP server stopped")
