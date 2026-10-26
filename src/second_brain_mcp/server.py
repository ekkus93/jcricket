"""MCP Streamable HTTP server exposing the two Second Brain tools."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from time import monotonic

import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.applications import Starlette
from starlette.responses import JSONResponse

from .auth import LocalAuthMiddleware, current_principal
from .config import AppConfig
from .ollama import OllamaClient
from .schemas import AskResponse, ModelInventory
from .service import SecondBrainService
from .store import ConversationStore

logger = logging.getLogger(__name__)


def create_app(config: AppConfig) -> Starlette:
    credentials = config.credentials()
    if not credentials:
        raise ValueError(
            "configure bearer tokens through token_env before starting the server"
        )
    if len(set(credentials.values())) != len(credentials):
        raise ValueError("each configured principal must use a distinct token")
    ollama = OllamaClient(config)
    service = SecondBrainService(
        config, ollama, ConversationStore(config.database_path)
    )
    mcp = FastMCP(
        "Second Brain",
        host=config.host,
        port=config.port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        max_request_body_size=config.limits.request_bytes,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[
                config.host,
                f"{config.host}:*",
                "localhost",
                "localhost:*",
                "127.0.0.1",
                "127.0.0.1:*",
                "[::1]",
                "[::1]:*",
            ],
            allowed_origins=[
                "http://localhost",
                "http://localhost:*",
                "http://127.0.0.1",
                "http://127.0.0.1:*",
                "http://[::1]",
                "http://[::1]:*",
            ],
        ),
    )

    @mcp.tool(
        description=(
            "Ask an independent, tool-free Ollama chatbot. Successful turns are saved "
            "to your isolated conversation."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
        structured_output=True,
    )
    async def ask_second_brain(
        ctx: Context,
        question: str,
        context: str | None = None,
        conversation_id: str | None = None,
        mode: str = "discuss",
        model_profile: str | None = None,
        model: str | None = None,
    ) -> AskResponse:
        request_id = ctx.request_id
        principal = current_principal()
        started = monotonic()
        try:
            result = await service.ask(
                principal,
                question,
                context,
                conversation_id,
                mode,
                model_profile,
                model,
            )
        except (ValueError, RuntimeError) as exc:
            logger.warning(
                "request_id=%s tool=ask_second_brain principal=%s "
                "status=error category=%s",
                request_id,
                principal,
                type(exc).__name__,
            )
            raise
        usage = result["usage"]
        logger.info(
            "request_id=%s tool=ask_second_brain principal=%s status=ok "
            "mode=%s profile=%s elapsed_ms=%s prompt_tokens=%s completion_tokens=%s",
            request_id,
            principal,
            mode,
            result["model_profile"],
            round((monotonic() - started) * 1000),
            usage["prompt_tokens"],
            usage["completion_tokens"],
        )
        return AskResponse.model_validate(result)

    @mcp.tool(
        description=(
            "List installed Ollama models and loaded status. Read-only; does not load, "
            "pull, run, or modify models."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        structured_output=True,
    )
    async def list_models(ctx: Context) -> ModelInventory:
        request_id = ctx.request_id
        principal = current_principal()
        started = monotonic()
        try:
            inventory = await ollama.models()
        except RuntimeError as exc:
            logger.warning(
                "request_id=%s tool=list_models principal=%s status=error category=%s",
                request_id,
                principal,
                type(exc).__name__,
            )
            raise
        logger.info(
            "request_id=%s tool=list_models principal=%s status=ok "
            "model_count=%d elapsed_ms=%d",
            request_id,
            principal,
            len(inventory["models"]),
            round((monotonic() - started) * 1000),
        )
        return ModelInventory.model_validate(inventory)

    app = mcp.streamable_http_app()
    mcp_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def app_lifespan(application):
        async with mcp_lifespan(application):
            try:
                yield
            finally:
                await ollama.close()

    app.router.lifespan_context = app_lifespan
    app.add_route(
        "/healthz", lambda request: JSONResponse({"status": "ok"}), methods=["GET"]
    )
    app.add_middleware(
        LocalAuthMiddleware,
        credentials=credentials,
        host=config.host,
        requests_per_minute=config.limits.requests_per_minute,
    )
    app.state.mcp_server = mcp
    app.state.service = service
    app.state.ollama = ollama
    return app


def run(config: AppConfig) -> None:
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
    uvicorn.run(
        create_app(config),
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
    )
