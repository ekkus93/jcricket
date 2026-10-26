"""Local bearer-token authentication and principal context."""

from __future__ import annotations

import asyncio
import hmac
import time
import uuid
from collections import defaultdict, deque
from contextvars import ContextVar
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

from .errors import SecondBrainError

_current_principal: ContextVar[str | None] = ContextVar(
    "second_brain_principal", default=None
)
_current_request_id: ContextVar[str | None] = ContextVar(
    "second_brain_request_id", default=None
)


def current_principal() -> str:
    principal = _current_principal.get()
    if not principal:
        raise SecondBrainError("unauthorized")
    return principal


def current_request_id() -> str:
    return _current_request_id.get() or "unknown"


class LocalAuthMiddleware:
    """Require a configured bearer token on MCP routes and enforce local host policy."""

    def __init__(
        self,
        app: ASGIApp,
        credentials: dict[str, str],
        host: str,
        requests_per_minute: int = 60,
    ) -> None:
        self.app = app
        self.credentials = {
            principal: token.encode("utf-8") for principal, token in credentials.items()
        }
        self.allowed_hosts = {host, "127.0.0.1", "localhost", "[::1]"}
        self.requests_per_minute = requests_per_minute
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._rate_lock = asyncio.Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex
        request_token = _current_request_id.set(request_id)

        async def correlated_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self._handle_http(scope, receive, correlated_send)
        finally:
            _current_request_id.reset(request_token)

    async def _handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        path = scope.get("path", "")
        if path == "/healthz":
            await _json(send, 200, b'{"status":"ok"}')
            return
        if path not in {"/mcp", "/mcp/"}:
            await _json(send, 404, b'{"error":"not found"}')
            return
        host_header = headers.get("host", "")
        host = urlsplit(f"//{host_header}").hostname or ""
        origin = headers.get("origin")
        origin_host = urlsplit(origin).hostname if origin else None
        allowed_hosts = {entry.strip("[]").lower() for entry in self.allowed_hosts}
        valid_origin = not origin or (
            urlsplit(origin).scheme in {"http", "https"}
            and origin_host is not None
            and origin_host.lower() in allowed_hosts
        )
        if host.lower() not in allowed_hosts or not valid_origin:
            await _json(send, 403, b'{"error":"untrusted host or origin"}')
            return
        auth = headers.get("authorization", "")
        scheme, _, token = auth.partition(" ")
        if (
            scheme.lower() != "bearer"
            or not token
            or not token.isascii()
            or any(ord(char) < 33 or ord(char) > 126 for char in token)
        ):
            await _json(send, 401, b'{"error":"authentication required"}')
            return
        presented = token.encode("latin-1")
        principal = next(
            (
                name
                for name, expected in self.credentials.items()
                if hmac.compare_digest(presented, expected)
            ),
            None,
        )
        if principal is None:
            await _json(send, 401, b'{"error":"invalid credentials"}')
            return
        now = time.monotonic()
        async with self._rate_lock:
            requests = self._requests[principal]
            while requests and now - requests[0] >= 60:
                requests.popleft()
            rate_limited = len(requests) >= self.requests_per_minute
            if not rate_limited:
                requests.append(now)
        if rate_limited:
            await _json(send, 429, b'{"error":"request rate exceeded"}')
            return
        token_context = _current_principal.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_principal.reset(token_context)


async def _json(send: Send, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
