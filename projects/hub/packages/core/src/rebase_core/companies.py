"""Companies: a project that needs people, and what an admin does with the request."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rebase_core.comments import CommentService
from rebase_core.errors import NotFound, ValidationFailed
from rebase_core.models import COMPANY_STATES, Company, User
from rebase_core.schemas import CompanyCreate, CompanyList, CompanyRead, StatusChange
from rebase_core.users import UserService

ENTITY = "company"
LIST_LIMIT_DEFAULT = 100
LIST_LIMIT_MAX = 500


def _to_read(row: Company, user: User) -> CompanyRead:
    """`referente`/`email` read off the linked `users` row since migration B (REB-281)
    dropped the request's own copies: a company's several requests over time all name
    the one person on file, not a free-text string each request could drift from."""
    return CompanyRead(
        id=row.id,
        nome_azienda=row.nome_azienda,
        referente=f"{user.nome} {user.cognome}".strip(),
        email=user.email,
        progetto=row.progetto,
        periodo_da=row.periodo_da,
        durata=row.durata,
        budget_giornaliero=row.budget_giornaliero,
        stato=row.stato,
        note=row.note,
        origine=row.origine,
        utm_source=row.utm_source,
        utm_medium=row.utm_medium,
        utm_campaign=row.utm_campaign,
        utm_content=row.utm_content,
        utm_term=row.utm_term,
        utm_id=row.utm_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class CompanyService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def request(self, data: CompanyCreate) -> CompanyRead:
        """Every request is a row: a company has several projects, and two requests a
        week apart are two things to answer, not one to merge. The referente's `users`
        row is get-or-created by lowercased email (REB-278), from the two fields the
        wizard collects (REB-279, decision (f)), and left as it was found on a repeat
        request: the answer's `referente`/`email` read off that one row (REB-281),
        whether or not it matches what this particular request said."""
        utm = data.utm.model_dump() if data.utm is not None and not data.utm.is_empty() else {}
        email = data.email.strip().lower()
        user = UserService(self.session).get_or_create(
            email, data.referente_nome, data.referente_cognome
        )
        row = Company(
            user_id=user.id,
            nome_azienda=data.nome_azienda,
            progetto=data.progetto,
            periodo_da=data.periodo_da,
            durata=data.durata,
            budget_giornaliero=data.budget_giornaliero,
            **utm,
        )
        self.session.add(row)
        self.session.commit()
        return _to_read(row, user)

    def list_recent(self, limit: int = LIST_LIMIT_DEFAULT, stato: str | None = None) -> CompanyList:
        limit = max(1, min(limit, LIST_LIMIT_MAX))
        stmt = select(Company, User).join(User, User.id == Company.user_id)
        count = select(func.count()).select_from(Company)
        if stato is not None:
            stmt = stmt.where(Company.stato == stato)
            count = count.where(Company.stato == stato)
        rows = self.session.execute(
            stmt.order_by(Company.created_at.desc(), Company.id.desc()).limit(limit)
        ).all()
        totale = self.session.scalar(count) or 0
        return CompanyList(totale=totale, items=[_to_read(row, user) for row, user in rows])

    def get(self, company_id: UUID) -> CompanyRead:
        """The row with its thread of comments, newest first. Only here: the list
        leaves `commenti` empty."""
        row, user = self._require(company_id)
        read = _to_read(row, user)
        read.commenti = CommentService(self.session).list(ENTITY, company_id)
        return read

    def set_status(self, company_id: UUID, change: StatusChange) -> CompanyRead:
        if change.stato not in COMPANY_STATES:
            raise ValidationFailed(ENTITY, "stato", f"uno fra {', '.join(COMPANY_STATES)}")
        row, user = self._require(company_id)
        row.stato = change.stato
        if change.note is not None:
            row.note = change.note.strip() or None
        self.session.commit()
        return _to_read(row, user)

    def _require(self, company_id: UUID) -> tuple[Company, User]:
        result = self.session.execute(
            select(Company, User)
            .join(User, User.id == Company.user_id)
            .where(Company.id == company_id)
        ).first()
        if result is None:
            raise NotFound(ENTITY, company_id)
        return result[0], result[1]
