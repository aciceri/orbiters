"""Identity: one `users` row per person, and the one way in -- the magic link -- for a
member and an admin alike (REB-278, design record 2026-09-17 §4).

Owns get-or-create by lowercased email, session open/close, and the magic link's
request-and-enter, moved out of the person-matching pieces `MemberService` and
`AdminService` each used to carry their own copy of. `MemberService` keeps what is
specific to the freelancer card; `AdminService` keeps the password login and the admin
list/CRUD, both untouched and still working for the SPA until REB-279/281.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rebase_core.config import Settings
from rebase_core.errors import NotFound, ValidationFailed
from rebase_core.mail import Mail, magic_link_mail
from rebase_core.models import USER_ROLES, MagicLinkToken, MemberLogin, MemberSession, User

ENTITY = "user"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class UserService:
    """`settings` is required for the session/magic-link methods (deadlines, the link's
    minutes, `hub_url`) and unused by the pure identity ones below, so a caller that
    only needs `by_email`/`get_or_create` -- `FreelancerService`, `CompanyService` --
    may construct this with `session` alone."""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings

    # ---- identity ----------------------------------------------------------------

    def by_email(self, email: str) -> User | None:
        lowered = email.strip().lower()
        return self.session.scalar(select(User).where(func.lower(User.email) == lowered))

    def get_or_create(
        self, email: str, nome: str = "", cognome: str = "", linkedin_url: str | None = None
    ) -> User:
        """The `users` row for this address, made on the spot when none exists yet: one
        row per lowercased email, never two for a repeat application or request racing
        itself, the same guard `Freelancer.apply` already keeps for its own table."""
        row = self.by_email(email)
        if row is not None:
            return row
        row = User(
            email=email.strip().lower(), nome=nome, cognome=cognome, linkedin_url=linkedin_url
        )
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.by_email(email)
            assert existing is not None
            return existing
        return row

    def list_admins(self) -> list[User]:
        """Every admin, oldest first, so the page reads as a history (ORB-123) -- the
        same order `AdminService.list` gave `admin_users`, now a filter on `users`."""
        return list(
            self.session.scalars(
                select(User).where(User.role == "admin").order_by(User.created_at, User.id)
            ).all()
        )

    def promote(
        self, email: str, nome: str | None = None, cognome: str | None = None
    ) -> tuple[User, bool]:
        """Whatever `users` row already answers to this address is promoted with one
        click and no form; an address with none yet needs `nome`/`cognome` to create a
        bare row first, no freelancer card invented for it (§1, Nav and Amministratori).
        The second element is whether a row was created, so the caller knows to mail a
        fresh promotion the same link everyone else gets."""
        row = self.by_email(email)
        created = row is None
        if row is None:
            nome, cognome = (nome or "").strip(), (cognome or "").strip()
            if not nome or not cognome:
                raise ValidationFailed(
                    ENTITY, "nome", "servono nome e cognome per un indirizzo nuovo"
                )
            row = User(email=email.strip().lower(), nome=nome, cognome=cognome)
            self.session.add(row)
        row.role = "admin"
        self.session.commit()
        return row, created

    def demote(self, user_id: UUID) -> User:
        """Sets `role = 'member'`, fully reversible since nothing is deleted."""
        row = self.session.get(User, user_id)
        if row is None:
            raise NotFound(ENTITY, user_id)
        row.role = "member"
        self.session.commit()
        return row

    def set_role(
        self, email: str, role: str, nome: str = "", cognome: str = ""
    ) -> tuple[User, bool]:
        """`rebase setrole`'s own shape: a minimal row created when none exists
        (`nome`/`cognome` required for it), the role set either way."""
        if role not in USER_ROLES:
            raise ValidationFailed(ENTITY, "role", f"uno fra {', '.join(USER_ROLES)}")
        row = self.by_email(email)
        created = row is None
        if row is None:
            nome, cognome = nome.strip(), cognome.strip()
            if not nome or not cognome:
                raise ValidationFailed(
                    ENTITY, "nome", "servono nome e cognome per un indirizzo nuovo"
                )
            row = User(email=email.strip().lower(), nome=nome, cognome=cognome)
            self.session.add(row)
        row.role = role
        self.session.commit()
        return row, created

    # ---- the way in ----------------------------------------------------------------

    def request_link(self, email: str, note: str | None = None) -> Mail | None:
        """The mail to send, or `None` when nobody with that address exists. Sweeps the
        person's spent and expired tokens first: nothing needs a cron."""
        assert self.settings is not None
        row = self.by_email(email)
        if row is None:
            return None
        now = datetime.now(UTC)
        self.session.execute(
            delete(MagicLinkToken).where(
                MagicLinkToken.user_id == row.id,
                or_(MagicLinkToken.used_at.is_not(None), MagicLinkToken.expires_at <= now),
            )
        )
        raw = secrets.token_urlsafe(32)
        self.session.add(
            MagicLinkToken(
                user_id=row.id,
                token_hash=_hash(raw),
                expires_at=now + timedelta(minutes=self.settings.magic_link_minutes),
            )
        )
        self.session.commit()
        link = f"{self.settings.hub_url.rstrip('/')}/entra?t={raw}"
        return magic_link_mail(row.email, link, self.settings.magic_link_minutes, note)

    def enter(self, raw_token: str) -> tuple[User, str] | None:
        """The person and the raw session token for the cookie, or `None` for a wrong,
        spent or expired link. Spent by a conditional update gated on it still being
        unused, so of two requests racing on the same raw token only one opens a
        session (`MemberService.enter`'s own reasoning, unchanged)."""
        assert self.settings is not None
        if not raw_token:
            return None
        now = datetime.now(UTC)
        token = self.session.scalar(
            select(MagicLinkToken).where(MagicLinkToken.token_hash == _hash(raw_token))
        )
        if token is None or token.used_at is not None or token.expires_at <= now:
            return None
        row = self.session.get(User, token.user_id)
        if row is None:
            return None
        spent = self.session.execute(
            update(MagicLinkToken)
            .where(MagicLinkToken.id == token.id, MagicLinkToken.used_at.is_(None))
            .values(used_at=now)
            .returning(MagicLinkToken.id)
        )
        if len(spent.scalars().all()) != 1:
            self.session.rollback()
            return None
        raw_session = secrets.token_urlsafe(32)
        self.session.add(
            MemberSession(
                user_id=row.id, token_hash=_hash(raw_session), expires_at=self._deadline(now)
            )
        )
        # The login itself, kept after the session is gone (ORB-158): same commit, so a
        # session never exists without its login and a login never without its session.
        self.session.add(MemberLogin(user_id=row.id, logged_at=now))
        self.session.commit()
        return row, raw_session

    def resolve(self, raw: str | None) -> User | None:
        """The person behind a cookie, or `None`. Slides the expiry on every hit and
        forgets a session past its deadline the moment it is presented."""
        assert self.settings is not None
        if not raw:
            return None
        session_row = self.session.scalar(
            select(MemberSession).where(MemberSession.token_hash == _hash(raw))
        )
        if session_row is None:
            return None
        now = datetime.now(UTC)
        if session_row.expires_at <= now:
            self.session.delete(session_row)
            self.session.commit()
            return None
        row = self.session.get(User, session_row.user_id)
        if row is None:
            return None
        session_row.expires_at = self._deadline(now)
        self.session.commit()
        return row

    def resolve_admin(self, raw: str | None) -> User | None:
        """`resolve`, checked for the admin role: `None` for a signed-out cookie and
        for a real, signed-in member alike -- the caller decides which is a 401 and
        which is a 403."""
        user = self.resolve(raw)
        if user is None or user.role != "admin":
            return None
        return user

    def close_session(self, raw: str | None) -> None:
        if not raw:
            return
        session_row = self.session.scalar(
            select(MemberSession).where(MemberSession.token_hash == _hash(raw))
        )
        if session_row is not None:
            self.session.delete(session_row)
            self.session.commit()

    def _deadline(self, now: datetime | None = None) -> datetime:
        assert self.settings is not None
        return (now or datetime.now(UTC)) + timedelta(days=self.settings.member_session_days)
