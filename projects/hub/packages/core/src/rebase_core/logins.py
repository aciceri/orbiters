"""Who entered the hub, and when: the numbers the admin area reads off `member_logins`.

The rows are written by `UserService.enter` and by nothing else (ORB-158); this module
only reads them. Since REB-278 a login is for any signed-in person, not only a
freelancer, so `user_id` is the join (`member_logins.freelancer_id` is written by
nothing after this deploy); `membri_totali` stays a count of `freelancers`, since the
page still reads as "how many of the community's cards have logged in". The shape is
`PerkService.guide_stats` (ORB-156), so the two admin pages read the same way.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rebase_core.models import Freelancer, MemberLogin, User
from rebase_core.schemas import LoginRead, LoginStats

RECENT_LOGINS = 20


class LoginService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def stats(self, now: datetime | None = None) -> LoginStats:
        moment = now or datetime.now(UTC)
        week_ago = moment - timedelta(days=7)
        totale = self.session.scalar(select(func.count()).select_from(MemberLogin)) or 0
        membri = self.session.scalar(select(func.count(func.distinct(MemberLogin.user_id)))) or 0
        membri_totali = self.session.scalar(select(func.count()).select_from(Freelancer)) or 0
        ultimi = (
            self.session.scalar(
                select(func.count())
                .select_from(MemberLogin)
                .where(MemberLogin.logged_at >= week_ago)
            )
            or 0
        )
        rows = self.session.execute(
            select(MemberLogin, User)
            .join(User, User.id == MemberLogin.user_id)
            .order_by(MemberLogin.logged_at.desc(), MemberLogin.id.desc())
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
