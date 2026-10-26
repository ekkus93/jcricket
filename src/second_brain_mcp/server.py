"""MCP Streamable HTTP server exposing the two Second Brain tools."""

from __future__ import annotations

import hashlib
import logging
from contextlib import asynccontextmanager
from time import monotonic
from typing import Literal

import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError
from starlette.applications import Starlette

from .auth import LocalAuthMiddleware, current_principal, current_request_id
from .config import AppConfig
from .errors import ERROR_LOG_LEVELS, SecondBrainError
from .ollama import OllamaClient
from .schemas import AskResponse, ModelInventory
from .service import SecondBrainService
from .store import ConversationStore

logger = logging.getLogger(__name__)


class SecondBrainMCP(FastMCP):
    """FastMCP server that returns tool errors as exactly ``<code>: <message>``."""

    async def call_tool(self, name, arguments):
        started = monotonic()
        if self._tool_manager.get_tool(name) is None:
            return self._error_result(
                name, "invalid_input", started, "invalid_input: unknown tool"
            )
        try:
            return await super().call_tool(name, arguments)
        except ToolError as exc:
            code, text = _tool_error(exc)
            if not isinstance(exc.__cause__, SecondBrainError):
                return self._error_result(name, code, started, text)
            return _error_content(text)

    def _error_result(
        self, name: str, code: str, started: float, text: str
    ) -> CallToolResult:
        """Log with the full tool-log field set, then build the error result."""
        try:
            rpc_id = str(self.get_context().request_id)
        except ValueError:
            rpc_id = "-"
        try:
            principal = current_principal()
        except SecondBrainError:
            principal = "-"
        logger.log(
            ERROR_LOG_LEVELS[code],
            "request_id=%s rpc_id=%s tool=%s principal=%s status=error "
            "category=%s mode=- profile=- model=- context_limit_tokens=- "
            "history_trimmed=- elapsed_ms=%s prompt_tokens=- completion_tokens=- "
            "conversation_id_hash=-",
            current_request_id(),
            rpc_id,
            name,
            principal,
            code,
            round((monotonic() - started) * 1000),
        )
        return _error_content(text)


def _error_content(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], isError=True)


def _tool_error(exc: ToolError) -> tuple[str, str]:
    cause = exc.__cause__
    if isinstance(cause, SecondBrainError):
        return cause.code, str(cause)
    if isinstance(cause, ValidationError) and cause.title.endswith("Arguments"):
        fields = sorted(
            {str(error["loc"][0]) for error in cause.errors() if error.get("loc")}
        )
        message = (
            "invalid value for " + ", ".join(fields)
            if fields
            else "the request is invalid"
        )
        return "invalid_input", f"invalid_input: {message}"
    logger.error(
        "request_id=%s unexpected_error_type=%s",
        current_request_id(),
        type(cause or exc).__name__,
    )
    return "internal_error", str(SecondBrainError("internal_error"))


def create_app(config: AppConfig) -> Starlette:
    credentials = config.credentials()
    ollama = OllamaClient(config)
    service = SecondBrainService(
        config, ollama, ConversationStore(config.database_path)
    )
    mcp = SecondBrainMCP(
        "Second Brain",
        debug=False,
        log_level=config.log_level,
        host=config.host,
        port=config.port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        max_request_body_size=config.limits.request_bytes,
        session_idle_timeout=1800,
        max_sessions=10000,
        warn_on_duplicate_tools=True,
        warn_on_duplicate_prompts=True,
        warn_on_duplicate_resources=True,
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
                *config.trusted_hosts,
                *(f"{host}:*" for host in config.trusted_hosts),
            ],
            allowed_origins=[
                "http://localhost",
                "http://localhost:*",
                "http://127.0.0.1",
                "http://127.0.0.1:*",
                "http://[::1]",
                "http://[::1]:*",
                *(f"https://{host}" for host in config.trusted_hosts),
                *(f"https://{host}:*" for host in config.trusted_hosts),
                *(f"http://{host}" for host in config.trusted_hosts),
                *(f"http://{host}:*" for host in config.trusted_hosts),
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
            response = AskResponse.model_validate(result)
        except SecondBrainError as exc:
            logger.log(
                ERROR_LOG_LEVELS[exc.code],
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
                "status=error category=internal_error mode=%s profile=%s model=%s "
                "context_limit_tokens=%s history_trimmed=%s "
                "elapsed_ms=%s prompt_tokens=%s completion_tokens=%s "
                "conversation_id_hash=%s",
                request_id,
                rpc_id,
                principal,
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
            logger.error(
                "request_id=%s unexpected_error_type=%s",
                request_id,
                type(exc).__name__,
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
        return response

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
            inventory = ModelInventory.model_validate(await ollama.models())
        except SecondBrainError as exc:
            logger.log(
                ERROR_LOG_LEVELS[exc.code],
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
                "status=error category=internal_error mode=- profile=- "
                "model=- context_limit_tokens=- history_trimmed=- elapsed_ms=%s "
                "prompt_tokens=- completion_tokens=- conversation_id_hash=-",
                request_id,
                rpc_id,
                principal,
                round((monotonic() - started) * 1000),
            )
            logger.error(
                "request_id=%s unexpected_error_type=%s",
                request_id,
                type(exc).__name__,
            )
            raise SecondBrainError("internal_error") from exc
        logger.info(
            "request_id=%s rpc_id=%s tool=list_models principal=%s status=ok "
            "category=- mode=- profile=- model=- context_limit_tokens=- "
            "history_trimmed=- elapsed_ms=%d prompt_tokens=- completion_tokens=- "
            "conversation_id_hash=-",
            request_id,
            rpc_id,
            principal,
            round((monotonic() - started) * 1000),
        )
        return inventory

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
    app.add_middleware(
        LocalAuthMiddleware,
        credentials=credentials,
        host=config.host,
        requests_per_minute=config.limits.requests_per_minute,
        trusted_hosts=config.trusted_hosts,
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
        workers=1,
    )
