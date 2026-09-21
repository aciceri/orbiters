"""PigroCRM's spaces, as the hub's admin area shows them: which exist, and whose they are.

The hub imports nothing from PigroCRM and never opens its database (DECISIONS.md,
2026-09-09). What it does is ask the CRM's own API, `GET /api/tenants/`, with the token
the CRM reads as `PIGROCRM_REGISTRY_TOKEN`, through the same HTTP seam the mail and the
pixel use. The registry knows who opened a space and when, not what is inside it, and
that is all this module claims to know too.

The one thing the hub adds is the owner: when the address that opened a space is a
`freelancers` row, the space names that member and points at their card (ORB-142).
"""

import json
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rebase_core.config import Settings
from rebase_core.http import MAX_BODY_BYTES, HttpCall
from rebase_core.models import Freelancer, User

REGISTRY_PATH = "/api/tenants/"


class PigroUnavailable(Exception):
    """The CRM did not answer with a list: a status other than 200, or a body that is not
    the registry. The message is the sentence the admin area shows."""


class RegistryRow(BaseModel):
    """One row as PigroCRM's `TenantRead` writes it. `id` is accepted and dropped: the
    hub has no use for the CRM's key."""

    model_config = ConfigDict(extra="ignore")

    slug: str
    owner_email: str
    created_at: datetime


class PigroMember(BaseModel):
    """The hub member who owns a space, enough to name them and link their card."""

    id: UUID
    nome: str
    cognome: str


class PigroSpace(BaseModel):
    slug: str
    owner_email: str
    created_at: datetime
    # Where the space answers, for the link on the row.
    url: str
    # `None` when nobody with that address filled in the hub's wizard.
    membro: PigroMember | None


class PigroSpaceList(BaseModel):
    totale: int
    items: list[PigroSpace]


_ROWS = TypeAdapter(list[RegistryRow])


class PigroRegistry:
    """Reads the registry over HTTP and matches each owner to a member. The session is
    the hub's own; the CRM is only ever reached through `http`."""

    def __init__(self, settings: Settings, http: HttpCall) -> None:
        self.settings = settings
        self.http = http

    def _base_url(self) -> str:
        return self.settings.pigro_api_url.rstrip("/")

    def _fetch_rows(self) -> list[RegistryRow]:
        """The registry's raw rows, exactly as `GET /api/tenants/` answers them: what
        `list_spaces` and `find_by_email` (REB-284) both read before matching it to the
        hub's own members, so the request and its error handling are typed once."""
        headers = {
            "Authorization": f"Bearer {self.settings.pigro_registry_token}",
            "Accept": "application/json",
        }
        try:
            status, body = self.http("GET", self._base_url() + REGISTRY_PATH, headers, b"")
        except Exception as exc:  # noqa: BLE001 - a refused connection, a DNS miss, a timeout
            raise PigroUnavailable("Pigro non risponde.") from exc
        if status != 200:
            raise PigroUnavailable(f"Pigro non ha risposto ({status}).")
        if len(body) > MAX_BODY_BYTES:
            raise PigroUnavailable("Pigro ha risposto qualcosa di troppo lungo.")
        try:
            return _ROWS.validate_python(json.loads(body))
        except (ValueError, ValidationError) as exc:
            raise PigroUnavailable("Pigro ha risposto qualcosa che non è un elenco.") from exc

    def list_spaces(self, session: Session) -> PigroSpaceList:
        rows = self._fetch_rows()
        members = self._members({row.owner_email.lower() for row in rows}, session)
        return PigroSpaceList(
            totale=len(rows),
            items=[
                PigroSpace(
                    slug=row.slug,
                    owner_email=row.owner_email,
                    created_at=row.created_at,
                    url=f"{self._base_url()}/{row.slug}/app/",
                    membro=members.get(row.owner_email.lower()),
                )
                for row in rows
            ],
        )

    def find_by_email(self, email: str, session: Session) -> PigroSpace | None:
        """Whether one address owns a space (REB-284's freelancer detail): the same
        registry `list_spaces` reads, matched case-insensitively to one address
        instead of listed whole. `None` for an address with no space, never an
        error -- the CRM not knowing about somebody is not a hub failure."""
        target = email.strip().lower()
        row = next((r for r in self._fetch_rows() if r.owner_email.lower() == target), None)
        if row is None:
            return None
        members = self._members({target}, session)
        return PigroSpace(
            slug=row.slug,
            owner_email=row.owner_email,
            created_at=row.created_at,
            url=f"{self._base_url()}/{row.slug}/app/",
            membro=members.get(target),
        )

    @staticmethod
    def _members(emails: set[str], session: Session) -> dict[str, PigroMember]:
        """The members behind those addresses, by lowercased address, in one query."""
        if not emails:
            return {}
        rows = session.execute(
            select(Freelancer.id, User.email, User.nome, User.cognome)
            .join(User, User.id == Freelancer.user_id)
            .where(func.lower(User.email).in_(emails))
        ).all()
        return {
            email.lower(): PigroMember(id=freelancer_id, nome=nome, cognome=cognome)
            for freelancer_id, email, nome, cognome in rows
        }
