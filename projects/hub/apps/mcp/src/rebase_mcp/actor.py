"""Who is calling, over HTTP: one admin per request, carried on a `ContextVar`.

Over stdio the admin is resolved once at start-up (`__main__`). Over HTTP every request
carries its own bearer, resolved by `rebase_mcp.http` and stamped on the ASGI scope;
`AdminFromRequest` is the SDK's middleware that copies it from `ctx.request.state` into
a `ContextVar` for the duration of the call, and `request_admin` is what `build_server`
reads it back through. A `ContextVar`, because the SDK dispatches tools both on the
event loop and in a thread pool, and it is the one primitive correct for both.
"""

import contextvars
from typing import Any

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.shared.exceptions import MCPError

from rebase_core.admin_tokens import AdminRead

_CURRENT_ADMIN: contextvars.ContextVar[AdminRead] = contextvars.ContextVar("mcp_request_admin")

ADMIN_STATE_KEY = "admin"


def request_admin() -> AdminRead:
    """`AdminProvider` for the HTTP transport: the admin bound to the current call."""
    try:
        return _CURRENT_ADMIN.get()
    except LookupError as exc:
        raise RuntimeError(
            "no request admin is bound: every tool over HTTP must run inside AdminFromRequest"
        ) from exc


class AdminFromRequest:
    """`ServerMiddleware`: binds the request's admin for the handler, then unbinds it.
    A request without one is refused rather than run as nobody: the ASGI layer stamps
    an admin on every authenticated request, so its absence is a programming error."""

    async def __call__(
        self, ctx: ServerRequestContext[Any, Any], call_next: CallNext
    ) -> HandlerResult:
        request = ctx.request
        admin = getattr(getattr(request, "state", None), ADMIN_STATE_KEY, None)
        if not isinstance(admin, AdminRead):
            raise MCPError(code=-32001, message="nessun amministratore dietro la richiesta")
        token = _CURRENT_ADMIN.set(admin)
        try:
            return await call_next(ctx)
        finally:
            _CURRENT_ADMIN.reset(token)
