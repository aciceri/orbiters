"""Talenti: every freelancer card and every bare sign-up as one list (REB-282).

«Developer e CTO» (`FreelancerService.list_recent`) and «Iscrizioni»
(`SignupService.list_recent`) read overlapping people out of two tables, and
`FreelancerService.list_recent`'s own `lead`/`totale_lead` pair already surfaces a
signup with no card beside the cards it counts (ORB-163) -- as a side channel next to
`items`, not a row of the same list. This module makes that merge a first-class read
model instead: one row per person, `stato` `lead` for the bare sign-ups and the
freelancer's own state otherwise, over the same two tables, which stay exactly as they
are (Lorenzo's recommendation on REB-282: a sign-up that later fills the wizard keeps
two UTM sets, and folding the tables would have to drop one).

`FreelancerService`, `SignupService`, and every existing caller of either --
`GET /api/hub/freelancers`, `GET /api/hub/signups`, the MCP tools -- are untouched:
this is an additional read model beside them, not a replacement of their own queries.
"""

from sqlalchemy import Subquery, func, select
from sqlalchemy.orm import Session

from rebase_core.freelancers import LEAD_STATE
from rebase_core.models import FREELANCER_STATES, Freelancer, Signup, User
from rebase_core.schemas import TalentoList, TalentoOrigine, TalentoRead

LIST_LIMIT_DEFAULT = 100
LIST_LIMIT_MAX = 500
_ORIGIN_FORM: TalentoOrigine = "form"
# `COMPILATA_DA`'s two values (`models.py`), named for what an admin reading the list
# actually asks: did the person write this themselves, through the wizard, or did an
# admin draft it from research.
_ORIGIN_BY_COMPILATA_DA: dict[str, TalentoOrigine] = {"persona": "wizard", "admin": "admin"}


def _card_emails() -> Subquery:
    """Lowercased addresses that already have a card: a bare sign-up (ORB-163) is one
    whose address is not among these. The same anti-join `FreelancerService._leads`
    runs, written again here rather than imported, so this module reads the same
    self-contained way every other service in this package does."""
    return (
        select(func.lower(User.email).label("email"))
        .join(Freelancer, Freelancer.user_id == User.id)
        .subquery()
    )


def _signup_read(row: Signup) -> TalentoRead:
    return TalentoRead(
        id=row.id,
        nome=row.nome,
        cognome=row.cognome,
        email=row.email,
        linkedin_url=row.linkedin_url,
        stato=LEAD_STATE,
        origine=_ORIGIN_FORM,
        utm_source=row.utm_source,
        created_at=row.created_at,
    )


def _card_read(row: Freelancer, user: User) -> TalentoRead:
    return TalentoRead(
        id=row.id,
        nome=user.nome,
        cognome=user.cognome,
        email=user.email,
        linkedin_url=user.linkedin_url,
        stato=row.stato,
        origine=_ORIGIN_BY_COMPILATA_DA.get(row.compilata_da, "wizard"),
        utm_source=row.utm_source,
        created_at=row.created_at,
    )


class TalentiService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_recent(self, limit: int = LIST_LIMIT_DEFAULT, stato: str | None = None) -> TalentoList:
        """Every card and every bare sign-up as one row, newest first, `stato` `lead`
        for the bare ones.

        Fetches at most `limit` rows from each table, newest first, and merges them in
        Python rather than with a SQL `UNION`: correct for a top-`limit` merge of two
        sources each already sorted newest-first, since no row outside either source's
        own top `limit` can land in the combined top `limit` -- at most `limit` rows
        from any table can sit ahead of it, whichever table it is in. `stato` filters
        the same way `FreelancerService.list_recent` does: `"lead"` selects the bare
        sign-ups alone, any other value selects `Freelancer.stato == stato` (an unknown
        one is simply an empty list, since nothing ever writes a `stato` outside
        `FREELANCER_STATES`), and `None` merges both.
        """
        limit = max(1, min(limit, LIST_LIMIT_MAX))
        items: list[TalentoRead] = []
        if stato is None or stato != LEAD_STATE:
            card_stmt = select(Freelancer, User).join(User, User.id == Freelancer.user_id)
            if stato is not None:
                card_stmt = card_stmt.where(Freelancer.stato == stato)
            cards = self.session.execute(
                card_stmt.order_by(Freelancer.created_at.desc(), Freelancer.id.desc()).limit(limit)
            ).all()
            items.extend(_card_read(row, user) for row, user in cards)
        if stato is None or stato == LEAD_STATE:
            card_emails = _card_emails()
            leads = self.session.scalars(
                select(Signup)
                .outerjoin(card_emails, card_emails.c.email == func.lower(Signup.email))
                .where(card_emails.c.email.is_(None))
                .order_by(Signup.created_at.desc(), Signup.id.desc())
                .limit(limit)
            ).all()
            items.extend(_signup_read(row) for row in leads)
        items.sort(key=lambda item: (item.created_at, str(item.id)), reverse=True)
        items = items[:limit]
        per_stato = self._counts()
        totale = sum(per_stato.values()) if stato is None else per_stato.get(stato, 0)
        return TalentoList(totale=totale, items=items, per_stato=per_stato)

    def _counts(self) -> dict[str, int]:
        """How many rows sit in each state, `lead` included, over the whole table --
        never bounded by a page's `limit`, since these are the numbers the admin area's
        tabs need beside it."""
        grouped = self.session.execute(
            select(Freelancer.stato, func.count()).group_by(Freelancer.stato)
        ).all()
        by_state: dict[str, int] = {stato: count for stato, count in grouped}
        counts = {stato: by_state.get(stato, 0) for stato in FREELANCER_STATES}
        card_emails = _card_emails()
        counts[LEAD_STATE] = (
            self.session.scalar(
                select(func.count())
                .select_from(Signup)
                .outerjoin(card_emails, card_emails.c.email == func.lower(Signup.email))
                .where(card_emails.c.email.is_(None))
            )
            or 0
        )
        return counts
