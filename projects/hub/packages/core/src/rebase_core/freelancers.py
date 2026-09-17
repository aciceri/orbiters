"""Freelancers: the wizard's applications, what an admin does with them, and since
ORB-155 the card an admin writes from a signup for the person to complete."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Subquery, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rebase_core.comments import CommentService
from rebase_core.cv_text import CvText, extract_text
from rebase_core.errors import NotFound, ValidationFailed
from rebase_core.models import (
    CV_MAX_BYTES,
    FREELANCER_STATES,
    UTM_COLUMNS,
    Freelancer,
    MemberLogin,
    Signup,
)
from rebase_core.schemas import (
    CvFile,
    FreelancerCreate,
    FreelancerDraft,
    FreelancerList,
    FreelancerRead,
    SignupListItem,
    StatusChange,
)

ENTITY = "freelancer"
# The pseudo-state the list filter uses for signups without a card (ORB-163): never
# stored on a row, since a lead has no row of its own.
LEAD_STATE = "lead"
LIST_LIMIT_DEFAULT = 100
LIST_LIMIT_MAX = 500
PDF_MAGIC = b"%PDF-"
# The sentence `apply` asks for in the magic-link mail sent instead of overwriting an
# address already on file (REB-272): one more line in `magic_link_mail`'s voice, not a
# mail of its own.
ALREADY_HAS_CARD_NOTE = (
    "Risulta già una scheda su rebase con questo indirizzo: la trovi e la modifichi "
    "dalla tua area."
)


def check_cv(content: bytes, filename: str, mime: str) -> tuple[str, str]:
    """A PDF, at most `CV_MAX_BYTES`, or a refusal naming the field.

    Decided on the bytes, never on the declared type alone: a browser says whatever the
    extension suggests, and the five bytes every PDF starts with are what the file is.
    Returns the filename and mime as they will be stored -- the mime normalised to the
    one type the bytes proved.
    """
    if not content:
        raise ValidationFailed(ENTITY, "cv", "serve il CV, in PDF")
    if len(content) > CV_MAX_BYTES:
        raise ValidationFailed(ENTITY, "cv", "il CV può pesare al massimo 5 MB")
    if not content.startswith(PDF_MAGIC):
        raise ValidationFailed(ENTITY, "cv", "il CV deve essere un PDF")
    name = (filename or "cv.pdf").strip().replace("\\", "/").rsplit("/", 1)[-1][:255] or "cv.pdf"
    return name, "application/pdf" if mime in (
        "",
        "application/pdf",
        "application/octet-stream",
    ) else "application/pdf"


def cv_of(row: Freelancer) -> CvFile:
    """The stored CV as a download, or `NotFound("cv", ...)` on a card born from a
    signup that the person has not completed yet (ORB-155). Shared with the member
    area, so the two downloads answer the same thing to the same row."""
    if row.cv_bytes is None or row.cv_filename is None or row.cv_mime is None:
        raise NotFound("cv", row.id)
    return CvFile(filename=row.cv_filename, mime=row.cv_mime, content=row.cv_bytes)


def _logins_per_card() -> Subquery:
    """How many times each card's owner entered and when last (ORB-158), as one grouped
    subquery the list joins once: two hundred people are not two hundred counts."""
    return (
        select(
            MemberLogin.freelancer_id,
            func.count().label("accessi"),
            func.max(MemberLogin.logged_at).label("ultimo_accesso"),
        )
        .group_by(MemberLogin.freelancer_id)
        .subquery()
    )


def _signed_up() -> Subquery:
    """Which addresses are also on the landing's list (ORB-161), lowercased once so the
    join lands on `uq_orbiters_signups_email_lower` rather than on a function per row."""
    return select(func.lower(Signup.email).label("email")).subquery()


def _read_with_logins(
    row: Freelancer, accessi: int | None, ultimo: datetime | None, signed_up: object
) -> FreelancerRead:
    read = FreelancerRead.model_validate(row)
    read.accessi = accessi or 0
    read.ultimo_accesso = ultimo
    read.provenienza = "form" if signed_up is not None else "landing"
    return read


class FreelancerService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def apply(
        self,
        data: FreelancerCreate,
        cv: bytes | None = None,
        cv_filename: str = "",
        cv_mime: str = "",
    ) -> FreelancerRead:
        """One row per address, written once. An address that already has a card is
        the same person applying again, but this route is public and unauthenticated,
        so from here that second application proves nothing about who is sending it
        (REB-272): it changes nothing on the existing row -- not the profile fields,
        not `compilata_da`, not the CV -- and the card is returned exactly as it was
        stored. `has_email` is what the caller checks first to know whether to send
        that person the magic-link mail instead, pointing them at the member area
        where an authenticated session, not an anonymous form post, is what may change
        their card, drafted by an admin (ORB-155) or filled by themselves already.

        **The CV is optional here.** A card without one is a state the model already
        had -- `cv_of` answers `NotFound` for it, `completa` is false, and the member
        area's `replace_cv` exists precisely to add it later -- and asking for a PDF
        before a person can finish the form was turning away people who did not have
        one to hand.

        `cv is None` is "no file was attached"; `cv == b""` is an attached file with no
        bytes in it, and that is a refusal like any other broken upload. The difference
        is the caller's to make, and this signature is what lets them make it.
        """
        email = data.email.strip().lower()
        row = self._find(email)
        if row is not None:
            return FreelancerRead.model_validate(row)
        stored: tuple[bytes, str, str] | None = None
        if cv is not None:
            stored = (cv, *check_cv(cv, cv_filename, cv_mime))
        utm = data.utm.model_dump() if data.utm is not None and not data.utm.is_empty() else {}
        row = Freelancer(email=email, **utm)
        self.session.add(row)
        if stored is not None:
            content, filename, mime = stored
            row.cv_bytes, row.cv_filename, row.cv_mime, row.cv_size = (
                content,
                filename,
                mime,
                len(content),
            )
        row.nome = data.nome
        row.cognome = data.cognome
        row.linkedin_url = data.linkedin_url
        row.tariffa_giornaliera = data.tariffa_giornaliera
        row.posizione = data.posizione
        row.remoto = data.remoto
        row.links = list(data.links)
        row.compilata_da = "persona"
        try:
            self.session.commit()
        except IntegrityError:
            # Two first applications racing on one address: the index decides, and the
            # loser discovers on retry that the winner's row now answers to `_find`.
            self.session.rollback()
            return self.apply(data, cv, cv_filename, cv_mime)
        return FreelancerRead.model_validate(row)

    def has_email(self, email: str) -> bool:
        """Whether a card already answers to `email`, lowercased and trimmed: what the
        public wizard route checks before calling `apply`, to know whether to send the
        existing magic-link mail rather than pretend a new card was written (REB-272)."""
        return self._find(email.strip().lower()) is not None

    def draft_from_signup(
        self, signup_id: UUID, data: FreelancerDraft, autore: str
    ) -> FreelancerRead:
        """A card written by an admin from what the public web says about a signup
        (ORB-155): the address and the attribution come from the signup, the answers
        from the research, the CV from nobody -- the person adds it from the member
        area. One row per address still: a second research on a card the admin wrote
        replaces the researched fields and leaves `stato`, `note` and the CV alone; a
        research on a card the person filled (`compilata_da == "persona"`) is refused,
        because their own words win. One comment in the thread names the sources, so
        whoever reads the card can check where it came from."""
        signup = self.session.get(Signup, signup_id)
        if signup is None:
            raise NotFound("signup", signup_id)
        email = signup.email.strip().lower()
        row = self._find(email)
        if row is not None and row.compilata_da == "persona":
            raise ValidationFailed(ENTITY, "email", "la persona ha già compilato la sua scheda")
        created = row is None
        if row is None:
            utm = {column: getattr(signup, column) for column in UTM_COLUMNS}
            row = Freelancer(email=email, **utm)
            self.session.add(row)
        row.nome = data.nome
        row.cognome = data.cognome
        row.linkedin_url = data.linkedin_url
        row.posizione = data.posizione
        row.tariffa_giornaliera = data.tariffa_giornaliera
        row.remoto = data.remoto
        row.links = list(data.links)
        row.compilata_da = "admin"
        try:
            self.session.commit()
        except IntegrityError:
            # Two first drafts racing on one address: the index decides, and the loser
            # drafts again on top of the winner's row.
            self.session.rollback()
            return self.draft_from_signup(signup_id, data, autore)
        sources = ", ".join(data.fonti)
        text = (
            f"Scheda creata dall'iscrizione del {signup.created_at:%d/%m/%Y}. Fonti: {sources}"
            if created
            else f"Scheda aggiornata dalla ricerca. Fonti: {sources}"
        )
        CommentService(self.session).add(ENTITY, row.id, text, autore)
        return self.get(row.id)

    def list_recent(
        self, limit: int = LIST_LIMIT_DEFAULT, stato: str | None = None
    ) -> FreelancerList:
        limit = max(1, min(limit, LIST_LIMIT_MAX))
        if stato == LEAD_STATE:
            lead, totale_lead = self._leads(limit)
            return FreelancerList(totale=0, items=[], totale_lead=totale_lead, lead=lead)
        lead, totale_lead = self._leads(limit) if stato is None else ([], 0)
        logins, signed = _logins_per_card(), _signed_up()
        stmt = (
            select(Freelancer, logins.c.accessi, logins.c.ultimo_accesso, signed.c.email)
            .outerjoin(logins, logins.c.freelancer_id == Freelancer.id)
            .outerjoin(signed, signed.c.email == func.lower(Freelancer.email))
        )
        count = select(func.count()).select_from(Freelancer)
        if stato is not None:
            stmt = stmt.where(Freelancer.stato == stato)
            count = count.where(Freelancer.stato == stato)
        rows = self.session.execute(
            stmt.order_by(Freelancer.created_at.desc(), Freelancer.id.desc()).limit(limit)
        ).all()
        totale = self.session.scalar(count) or 0
        return FreelancerList(
            totale=totale,
            items=[
                _read_with_logins(row, accessi, ultimo, signed_up)
                for row, accessi, ultimo, signed_up in rows
            ],
            totale_lead=totale_lead,
            lead=lead,
        )

    def _leads(self, limit: int) -> tuple[list[SignupListItem], int]:
        """Signups whose address has no card (ORB-163), newest first, and how many
        there are: one anti-join on the two case-insensitive indexes."""
        no_card = Freelancer.id.is_(None)
        base = select(Signup).outerjoin(
            Freelancer, func.lower(Freelancer.email) == func.lower(Signup.email)
        )
        rows = self.session.scalars(
            base.where(no_card).order_by(Signup.created_at.desc(), Signup.id.desc()).limit(limit)
        ).all()
        totale = (
            self.session.scalar(
                select(func.count())
                .select_from(Signup)
                .outerjoin(Freelancer, func.lower(Freelancer.email) == func.lower(Signup.email))
                .where(no_card)
            )
            or 0
        )
        return [SignupListItem.model_validate(row) for row in rows], totale

    def get(self, freelancer_id: UUID) -> FreelancerRead:
        """The row with its thread of comments, newest first. Only here: the list
        leaves `commenti` empty."""
        row = self._require(freelancer_id)
        logins = _logins_per_card()
        counted = self.session.execute(
            select(logins.c.accessi, logins.c.ultimo_accesso).where(
                logins.c.freelancer_id == row.id
            )
        ).first()
        signed_up = self.session.scalar(
            select(Signup.id).where(func.lower(Signup.email) == row.email.lower())
        )
        accessi, ultimo = counted if counted is not None else (None, None)
        read = _read_with_logins(row, accessi, ultimo, signed_up)
        read.commenti = CommentService(self.session).list(ENTITY, freelancer_id)
        return read

    def cv(self, freelancer_id: UUID) -> CvFile:
        return cv_of(self._require(freelancer_id))

    def cv_text(self, freelancer_id: UUID) -> CvText:
        """The stored CV as text (ORB-206), or `NotFound("cv", ...)` like `cv`: a card
        born from a signup has no file to read, and that is a sentence, not a scan."""
        file = cv_of(self._require(freelancer_id))
        return extract_text(file.content, file.filename)

    def set_status(self, freelancer_id: UUID, change: StatusChange) -> FreelancerRead:
        if change.stato not in FREELANCER_STATES:
            raise ValidationFailed(ENTITY, "stato", f"uno fra {', '.join(FREELANCER_STATES)}")
        row = self._require(freelancer_id)
        row.stato = change.stato
        if change.note is not None:
            row.note = change.note.strip() or None
        self.session.commit()
        return FreelancerRead.model_validate(row)

    def _require(self, freelancer_id: UUID) -> Freelancer:
        row = self.session.get(Freelancer, freelancer_id)
        if row is None:
            raise NotFound(ENTITY, freelancer_id)
        return row

    def _find(self, email: str) -> Freelancer | None:
        return self.session.scalar(select(Freelancer).where(func.lower(Freelancer.email) == email))
