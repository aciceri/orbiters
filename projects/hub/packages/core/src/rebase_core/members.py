"""The member area: the freelancer card, and what its owner may change once signed in.

The way in -- the magic link, session open/close, `resolve` -- moved to
`rebase_core.users` (REB-278): a person signs in as a `users` row, member or admin
alike, and this module keeps only what is specific to the freelancer card. Every change
the person makes is a comment in the row's thread (ORB-59), so the admin sees what moved
without an audit table.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rebase_core.comments import CommentService
from rebase_core.errors import NotFound
from rebase_core.freelancers import check_cv, cv_of
from rebase_core.models import AUTORE_MAX_LENGTH, Freelancer, User
from rebase_core.schemas import CvFile, MemberLookup, MemberProfile, MemberUpdate, MeRead

ENTITY = "freelancer"
# What the comment calls each field, in the admin's language, in the wizard's order.
FIELD_LABELS: dict[str, str] = {
    "nome": "nome",
    "cognome": "cognome",
    "linkedin_url": "profilo LinkedIn",
    "tariffa_giornaliera": "tariffa giornaliera",
    "posizione": "posizione",
    "remoto": "modalità di lavoro",
    "links": "link",
}
# The three fields a freelancer card shares with its `users` row: legitimately changing
# one here also changes it there, in the same commit, so `GET /me` never reads a stale
# name the person just corrected (§3's "every writer and reader" table).
_IDENTITY_FIELDS = {"nome", "cognome", "linkedin_url"}


class MemberService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- the identity behind a card ---------------------------------------------------

    def card_for_user(self, user_id: UUID) -> Freelancer | None:
        return self.session.scalar(select(Freelancer).where(Freelancer.user_id == user_id))

    def require_card(self, user_id: UUID) -> Freelancer:
        """The freelancer card for a signed-in person, or a 404 named "scheda": an
        admin with none yet is a new case this record's card-less admin introduces
        (design record §4)."""
        row = self.card_for_user(user_id)
        if row is None:
            raise NotFound("scheda", user_id)
        return row

    def me_read(self, user_id: UUID) -> MeRead:
        """The full `GET /me` shape for whoever `user_id` names: the identity off
        `users`, plus the card's own fields when one exists, blank otherwise."""
        user = self.session.get(User, user_id)
        if user is None:
            raise NotFound("user", user_id)
        card = self.card_for_user(user_id)
        if card is None:
            return MeRead(
                id=user.id,
                nome=user.nome,
                cognome=user.cognome,
                email=user.email,
                linkedin_url=user.linkedin_url,
                role=user.role,
                created_at=user.created_at,
                updated_at=user.updated_at,
                ha_scheda=False,
            )
        return MeRead(
            id=user.id,
            nome=user.nome,
            cognome=user.cognome,
            email=user.email,
            linkedin_url=user.linkedin_url,
            role=user.role,
            created_at=user.created_at,
            updated_at=user.updated_at,
            ha_scheda=True,
            cv_filename=card.cv_filename,
            cv_size=card.cv_size,
            tariffa_giornaliera=card.tariffa_giornaliera,
            posizione=card.posizione,
            remoto=card.remoto,
            links=list(card.links),
        )

    # ---- what another product may ask ------------------------------------------------

    def lookup(self, email: str) -> MemberLookup:
        """Whether a freelancer with that address exists, and their two names if so
        (ORB-173). The same match as `uq_freelancers_email_lower`, so the answer agrees
        with what the wizard would have refused as a duplicate. An unknown address is
        `membro=False` and never an error: the caller is PigroCRM's signup, and a person
        who is not in the community is the ordinary case there, not a fault."""
        row = self._by_email(email.strip().lower())
        if row is None:
            return MemberLookup(membro=False)
        return MemberLookup(membro=True, nome=row.nome, cognome=row.cognome)

    # ---- what they see and change -----------------------------------------------------

    def profile(self, freelancer_id: UUID) -> MemberProfile:
        return MemberProfile.model_validate(self._require(freelancer_id))

    def update(self, freelancer_id: UUID, data: MemberUpdate) -> MemberProfile:
        """Applies the seven answers and leaves one comment naming the ones that moved,
        signed with the person's name after the change. Nothing moved, no comment --
        unless the card was an admin's draft from a signup (ORB-155): saving it, even
        unchanged, makes it the person's (`compilata_da = "persona"`), and the thread
        says so. `stato`, `note` and the attribution are never touched here. A changed
        `nome`/`cognome`/`linkedin_url` is also written onto the linked `users` row, in
        the same commit, so `GET /me` reads the correction on its very next call."""
        row = self._require(freelancer_id)
        changed: list[str] = []
        identity_changed = False
        for field, label in FIELD_LABELS.items():
            value = getattr(data, field)
            if field == "links":
                value = list(value)
            if getattr(row, field) != value:
                setattr(row, field, value)
                changed.append(label)
                if field in _IDENTITY_FIELDS:
                    identity_changed = True
        taken_over = row.compilata_da != "persona"
        if not changed and not taken_over:
            return MemberProfile.model_validate(row)
        row.compilata_da = "persona"
        if identity_changed:
            user = self.session.get(User, row.user_id)
            if user is not None:
                user.nome, user.cognome, user.linkedin_url = row.nome, row.cognome, row.linkedin_url
        self.session.commit()
        if changed:
            self._comment(row, f"Profilo aggiornato dalla persona: {', '.join(changed)}")
        else:
            self._comment(row, "Scheda confermata dalla persona")
        return MemberProfile.model_validate(row)

    def replace_cv(
        self, freelancer_id: UUID, content: bytes, filename: str, mime: str
    ) -> MemberProfile:
        """The same check as the wizard's (`check_cv`), then the bytes replace the old
        ones and the thread says so."""
        filename, mime = check_cv(content, filename, mime)
        row = self._require(freelancer_id)
        first = row.cv_bytes is None
        row.cv_bytes, row.cv_filename, row.cv_mime, row.cv_size = (
            content,
            filename,
            mime,
            len(content),
        )
        row.compilata_da = "persona"
        self.session.commit()
        self._comment(row, "CV caricato dalla persona" if first else "CV aggiornato dalla persona")
        return MemberProfile.model_validate(row)

    def cv(self, freelancer_id: UUID) -> CvFile:
        return cv_of(self._require(freelancer_id))

    # ---- helpers ---------------------------------------------------------------------

    def _comment(self, row: Freelancer, text: str) -> None:
        author = f"{row.nome} {row.cognome}"[:AUTORE_MAX_LENGTH]
        CommentService(self.session).add(ENTITY, row.id, text, author)

    def _require(self, freelancer_id: UUID) -> Freelancer:
        row = self.session.get(Freelancer, freelancer_id)
        if row is None:
            raise NotFound(ENTITY, freelancer_id)
        return row

    def _by_email(self, email: str) -> Freelancer | None:
        return self.session.scalar(select(Freelancer).where(func.lower(Freelancer.email) == email))
