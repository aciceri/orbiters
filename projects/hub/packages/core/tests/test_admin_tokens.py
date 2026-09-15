"""An admin's personal tokens: minted once, resolved to the admin, refused uniformly."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from rebase_core.admin import AdminRead, AdminService
from rebase_core.admin_tokens import INVALID_TOKEN, TOKEN_PREFIX, AdminTokenService
from rebase_core.config import Settings
from rebase_core.errors import NotFound, ValidationFailed


@pytest.fixture
def ivan(hub_engine: Engine, hub_session: Session) -> Iterator[AdminRead]:
    settings = Settings(
        database_url=hub_engine.url.render_as_string(hide_password=False),
        _env_file=None,  # type: ignore[call-arg]
    )
    service = AdminService(hub_session, settings)
    yield service.create("ivan@orbiters.it", "Ivan", "una-password-lunga")
    hub_session.rollback()
    for table in ("admin_tokens", "admin_sessions", "admin_users"):
        hub_session.execute(text(f"DELETE FROM {table}"))
    hub_session.commit()


def test_a_token_is_minted_once_and_resolves_to_its_admin(
    ivan: AdminRead, hub_session: Session
) -> None:
    tokens = AdminTokenService(hub_session)
    read, raw = tokens.create(ivan.id, "  Claude Code ")
    assert raw.startswith(TOKEN_PREFIX) and len(raw) > 30
    assert read.nome == "Claude Code"
    assert read.prefix == raw[:12] and read.last_used_at is None and read.revoked_at is None
    stored = hub_session.execute(text("SELECT token_hash, prefix FROM admin_tokens")).one()
    assert raw not in stored[0] and stored[1] == read.prefix

    resolved = tokens.resolve(raw)
    assert resolved.id == ivan.id and resolved.email == "ivan@orbiters.it"
    [listed] = tokens.list(ivan.id)
    assert listed.id == read.id and listed.last_used_at is not None


def test_every_failure_of_resolve_is_the_same_sentence(
    ivan: AdminRead, hub_session: Session
) -> None:
    tokens = AdminTokenService(hub_session)
    _, raw = tokens.create(ivan.id, "Claude Code")
    for bad in (None, "", "Bearer x", "pgc_" + "a" * 40, TOKEN_PREFIX + "sconosciuto"):
        with pytest.raises(ValidationFailed) as refused:
            tokens.resolve(bad)
        assert refused.value.details["reason"] == INVALID_TOKEN

    revoked = tokens.revoke(ivan.id, tokens.list(ivan.id)[0].id)
    assert revoked.revoked_at is not None
    with pytest.raises(ValidationFailed) as refused:
        tokens.resolve(raw)
    assert refused.value.details["reason"] == INVALID_TOKEN
    # Revoking again keeps the first date, and the list still shows the row.
    assert tokens.revoke(ivan.id, revoked.id).revoked_at == revoked.revoked_at
    assert [row.id for row in tokens.list(ivan.id)] == [revoked.id]

    _, again = tokens.create(ivan.id, "Cursor")
    hub_session.execute(text("UPDATE admin_users SET attivo = false"))
    hub_session.commit()
    with pytest.raises(ValidationFailed) as refused:
        tokens.resolve(again)
    assert refused.value.details["reason"] == INVALID_TOKEN


def test_a_token_belongs_to_its_admin_alone(ivan: AdminRead, hub_session: Session) -> None:
    tokens = AdminTokenService(hub_session)
    read, _ = tokens.create(ivan.id, "Claude Code")
    with pytest.raises(NotFound):
        tokens.revoke(uuid4(), read.id)
    assert tokens.list(uuid4()) == []
    with pytest.raises(NotFound):
        tokens.create(uuid4(), "Nessuno")
    with pytest.raises(ValidationFailed):
        tokens.create(ivan.id, "   ")
