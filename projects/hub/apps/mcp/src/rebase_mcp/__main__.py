"""`python -m rebase_mcp`: the server over stdio, as one admin.

Reads a personal token from `REBASE_MCP_TOKEN` and resolves it once, before the
first message: a process nobody has a token for does not start (REB-213). The HTTP
transport is `rebase_mcp.http`, served by the hub API; this one is for a developer's
client and for a shell on the host.
"""

import os
import sys

from rebase_core.admin_tokens import AdminTokenService
from rebase_core.config import get_settings
from rebase_core.db import create_engine_from_settings, session_factory
from rebase_core.errors import DomainError
from rebase_core.http import urllib_call
from rebase_mcp.server import build_server

TOKEN_VARIABLE = "REBASE_MCP_TOKEN"


def main() -> int:
    settings = get_settings()
    factory = session_factory(create_engine_from_settings(settings))
    session = factory()
    try:
        admin = AdminTokenService(session).resolve(os.environ.get(TOKEN_VARIABLE))
    except DomainError:
        print(
            f"Serve un token personale di un amministratore in {TOKEN_VARIABLE}: "
            "si crea dall'area admin («Agenti») o con `rebase createtoken`.",
            file=sys.stderr,
        )
        return 1
    finally:
        session.close()
    build_server(factory, lambda: admin, settings=settings, http=urllib_call).run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
