"""MCP Streamable HTTP server exposing the two Second Brain tools."""

from __future__ import annotations

import hashlib
import logging
from contextlib import asynccontextmanager
from time import monotonic
from typing import Literal

import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.applications import Starlette
from starlette.responses import JSONResponse

from .auth import LocalAuthMiddleware, current_principal, current_request_id
from .config import AppConfig
from .errors import SecondBrainError
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
        mode: Literal["discuss", "brainstorm", "critic", "review", "solve"] = "discuss",
        model_profile: Literal["4k", "32k", "128k", "256k"] | None = None,
        model: str | None = None,
    ) -> AskResponse:
        request_id = current_request_id()
        rpc_id = str(ctx.request_id)
        principal = "unknown"
        started = monotonic()
        conversation_hash = _conversation_hash(conversation_id)
        try:
            principal = current_principal()
            result = await service.ask(
                principal,
                question,
                context,
                conversation_id,
                mode,
                model_profile,
                model,
            )
        except SecondBrainError as exc:
            logger.error(
                "request_id=%s rpc_id=%s tool=ask_second_brain principal=%s "
                "status=error category=%s mode=%s profile=%s model=%s "
                "context_limit_tokens=%s history_trimmed=%s elapsed_ms=%s "
                "prompt_tokens=%s completion_tokens=%s conversation_id_hash=%s",
                request_id,
                rpc_id,
                principal,
                exc.code,
                mode,
                model_profile or "-",
                model or "-",
                "-",
                "-",
                round((monotonic() - started) * 1000),
                "-",
                "-",
                conversation_hash,
            )
            raise
        except Exception as exc:
            logger.debug("unexpected ask_second_brain failure", exc_info=True)
            logger.error(
                "request_id=%s rpc_id=%s tool=ask_second_brain principal=%s "
                "status=error category=internal_error error_type=%s mode=%s "
                "profile=%s model=%s context_limit_tokens=%s history_trimmed=%s "
                "elapsed_ms=%s prompt_tokens=%s completion_tokens=%s "
                "conversation_id_hash=%s",
                request_id,
                rpc_id,
                principal,
                type(exc).__name__,
                mode,
                model_profile or "-",
                model or "-",
                "-",
                "-",
                round((monotonic() - started) * 1000),
                "-",
                "-",
                conversation_hash,
            )
            raise SecondBrainError("internal_error") from exc
        usage = result["usage"]
        logger.info(
            "request_id=%s rpc_id=%s tool=ask_second_brain principal=%s status=ok "
            "category=- mode=%s profile=%s model=%s context_limit_tokens=%s "
            "history_trimmed=%s elapsed_ms=%s prompt_tokens=%s completion_tokens=%s "
            "conversation_id_hash=%s",
            request_id,
            rpc_id,
            principal,
            mode,
            result["model_profile"],
            result["model"],
            result["context_limit_tokens"],
            result["history_trimmed"],
            round((monotonic() - started) * 1000),
            usage["prompt_tokens"],
            usage["completion_tokens"],
            _conversation_hash(result["conversation_id"]),
        )
        return AskResponse.model_validate(result)

    @mcp.tool(
        description=(
            "List up to 200 installed Ollama models and loaded status. Configured "
            "and approved models are included when the result is truncated. "
            "Read-only; does not load, pull, run, or modify models."
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
        request_id = current_request_id()
        rpc_id = str(ctx.request_id)
        principal = "unknown"
        started = monotonic()
        try:
            principal = current_principal()
            inventory = await ollama.models()
        except SecondBrainError as exc:
            logger.error(
                "request_id=%s rpc_id=%s tool=list_models principal=%s status=error "
                "category=%s mode=- profile=- model=- context_limit_tokens=- "
                "history_trimmed=- elapsed_ms=%s prompt_tokens=- completion_tokens=- "
                "conversation_id_hash=-",
                request_id,
                rpc_id,
                principal,
                exc.code,
                round((monotonic() - started) * 1000),
            )
            raise
        except Exception as exc:
            logger.debug("unexpected list_models failure", exc_info=True)
            logger.error(
                "request_id=%s rpc_id=%s tool=list_models principal=%s "
                "status=error category=internal_error error_type=%s mode=- profile=- "
                "model=- context_limit_tokens=- history_trimmed=- elapsed_ms=%s "
                "prompt_tokens=- completion_tokens=- conversation_id_hash=-",
                request_id,
                rpc_id,
                principal,
                type(exc).__name__,
                round((monotonic() - started) * 1000),
            )
            raise SecondBrainError("internal_error") from exc
        logger.info(
            "request_id=%s rpc_id=%s tool=list_models principal=%s status=ok "
            "category=- mode=- profile=- model=- context_limit_tokens=- "
            "history_trimmed=- elapsed_ms=%d prompt_tokens=- completion_tokens=- "
            "conversation_id_hash=- model_count=%d",
            request_id,
            rpc_id,
            principal,
            round((monotonic() - started) * 1000),
            len(inventory["models"]),
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


def _conversation_hash(conversation_id: str | None) -> str:
    if not conversation_id:
        return "-"
    return hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:8]


def run(config: AppConfig) -> None:
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
    uvicorn.run(
        create_app(config),
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
    )
