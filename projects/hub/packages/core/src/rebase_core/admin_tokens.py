"""Personal tokens of the admins, for agents: the credential the MCP server takes.

The shape of the CRM's `PatService`, written again because the hub imports nothing from
the CRM, and without the activity timeline the hub does not have. The value is minted
here, returned once and never stored; what the table holds is its sha256, which is a
deterministic lookup key and safe because the value is 32 random bytes, not a password
somebody chose. Every way `resolve` can fail is the same sentence: an unknown value, a
revoked token and a deactivated or demoted owner are not told apart, so a leaked token
is not an oracle for whether it is still worth using.

Since REB-278 the owner is a `users` row with `role == 'admin'` (`user_id`), not an
`admin_users` row: `AdminRead` is unchanged in shape, only in what it is read off."""

import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from rebase_core.admin import AdminRead
from rebase_core.errors import NotFound, ValidationFailed
from rebase_core.models import NAME_MAX_LENGTH, AdminToken, User

ENTITY = "token"
TOKEN_PREFIX = "reb_"
PREFIX_VISIBLE_CHARS = 8
INVALID_TOKEN = "Token non valido"
DEFAULT_NAME = "Claude Code"


class AdminTokenRead(BaseModel):
    """A token as the admin area lists it: never the hash, never the value."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def is_token(raw: str | None) -> bool:
    """Whether a string could be one of ours: a bearer that is not is no credential at
    all, and the caller refuses it without a read."""
    return bool(raw) and raw.startswith(TOKEN_PREFIX)  # type: ignore[union-attr]


class AdminTokenService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, user_id: UUID, nome: str) -> tuple[AdminTokenRead, str]:
        """A fresh token for the admin, with the name they gave it. The raw value is the
        second element, returned exactly once."""
        nome = nome.strip()
        if not nome:
            raise ValidationFailed(ENTITY, "nome", "serve un nome")
        if len(nome) > NAME_MAX_LENGTH:
            raise ValidationFailed(ENTITY, "nome", f"al massimo {NAME_MAX_LENGTH} caratteri")
        owner = self.session.get(User, user_id)
        if owner is None or owner.role != "admin" or not owner.attivo:
            raise NotFound("admin", user_id)
        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        row = AdminToken(
            user_id=user_id,
            nome=nome,
            token_hash=_digest(raw),
            prefix=raw[: len(TOKEN_PREFIX) + PREFIX_VISIBLE_CHARS],
        )
        self.session.add(row)
        self.session.commit()
        return AdminTokenRead.model_validate(row), raw

    def revoke(self, user_id: UUID, token_id: UUID) -> AdminTokenRead:
        """Ends a token of this admin. Another admin's token is `NotFound`, so the route
        cannot be used to learn that it exists. Revoking twice keeps the first date."""
        row = self.session.scalar(
            select(AdminToken).where(AdminToken.id == token_id, AdminToken.user_id == user_id)
        )
        if row is None:
            raise NotFound(ENTITY, token_id)
        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            self.session.commit()
        return AdminTokenRead.model_validate(row)

    def resolve(self, raw: str | None) -> AdminRead:
        """The admin behind a token, or one `ValidationFailed` for every failure. Stamps
        `last_used_at`, which is what the list shows as «ultimo uso». `populate_existing`
        forces a fresh read of the owner: `role`/`attivo` can change between two calls
        against the same long-lived session (an MCP server's, in production; a test's
        raw `UPDATE` in this package's own suite), and a cached, stale copy would let a
        just-demoted or just-deactivated admin's token keep resolving."""
        if not is_token(raw):
            raise ValidationFailed(ENTITY, "token", INVALID_TOKEN)
        assert raw is not None
        row = self.session.scalar(select(AdminToken).where(AdminToken.token_hash == _digest(raw)))
        if row is None or row.revoked_at is not None:
            raise ValidationFailed(ENTITY, "token", INVALID_TOKEN)
        owner = self.session.get(User, row.user_id, populate_existing=True)
        if owner is None or owner.role != "admin" or not owner.attivo:
            raise ValidationFailed(ENTITY, "token", INVALID_TOKEN)
        row.last_used_at = datetime.now(UTC)
        self.session.commit()
        return AdminRead.model_validate(owner)

    # Last on purpose: a method named `list` rebinds the name in the class body, and a
    # bare `list[...]` annotation below it would fail at import time.
    def list(self, user_id: UUID) -> list[AdminTokenRead]:
        """The admin's own tokens, newest first, revoked ones included: a list that hides
        what was revoked cannot show that somebody revoked it."""
        rows = self.session.scalars(
            select(AdminToken)
            .where(AdminToken.user_id == user_id)
            .order_by(AdminToken.created_at.desc(), AdminToken.id.desc())
        ).all()
        return [AdminTokenRead.model_validate(row) for row in rows]
