"""Who entered the hub, and when: the numbers the admin area reads off `logins`.

The rows are written by `UserService.enter` and by nothing else (ORB-158); this module
only reads them. Since REB-278 a login is for any signed-in person, not only a
freelancer, so `user_id` is the join; migration B (REB-281) renamed the table from
`member_logins` to `logins`, once "member" stopped describing who is in it, and dropped
the `freelancer_id` it replaced. `membri_totali` stays a count of `freelancers`, since
the page still reads as "how many of the community's cards have logged in". The shape is
`PerkService.guide_stats` (ORB-156), so the two admin pages read the same way.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rebase_core.models import Freelancer, Login, User
from rebase_core.schemas import LoginRead, LoginStats

RECENT_LOGINS = 20
# The short list a card's own detail shows (REB-284), well below the admin's own
# `/logins` page: an admin reading one person does not need their last twenty.
RECENT_LOGINS_FOR_CARD = 5


class LoginService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def stats(self, now: datetime | None = None) -> LoginStats:
        moment = now or datetime.now(UTC)
        week_ago = moment - timedelta(days=7)
        totale = self.session.scalar(select(func.count()).select_from(Login)) or 0
        membri = self.session.scalar(select(func.count(func.distinct(Login.user_id)))) or 0
        membri_totali = self.session.scalar(select(func.count()).select_from(Freelancer)) or 0
        ultimi = (
            self.session.scalar(
                select(func.count()).select_from(Login).where(Login.logged_at >= week_ago)
            )
            or 0
        )
        rows = self.session.execute(
            select(Login, User)
            .join(User, User.id == Login.user_id)
            .order_by(Login.logged_at.desc(), Login.id.desc())
            .limit(RECENT_LOGINS)
        ).all()
        return LoginStats(
            totale=totale,
            membri=membri,
            membri_totali=membri_totali,
            ultimi_7_giorni=ultimi,
            recenti=[
                LoginRead(
                    id=login.id,
                    user_id=login.user_id,
                    nome=person.nome,
                    cognome=person.cognome,
                    email=person.email,
                    logged_at=login.logged_at,
                )
                for login, person in rows
            ],
        )

    def for_user(self, user_id: UUID, limit: int = RECENT_LOGINS_FOR_CARD) -> list[LoginRead]:
        """The last few times this one person entered (REB-284's freelancer detail):
        the same shape `stats` reads for everybody, scoped to a single `user_id`
        instead of grouped across the whole hub."""
        rows = self.session.execute(
            select(Login, User)
            .join(User, User.id == Login.user_id)
            .where(Login.user_id == user_id)
            .order_by(Login.logged_at.desc(), Login.id.desc())
            .limit(limit)
        ).all()
        return [
            LoginRead(
                id=login.id,
                user_id=login.user_id,
                nome=person.nome,
                cognome=person.cognome,
                email=person.email,
                logged_at=login.logged_at,
            )
            for login, person in rows
        ]
