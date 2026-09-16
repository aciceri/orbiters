from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pigrocrm.core.auth.models import User
from pigrocrm.core.digest.models import Digest


def test_a_user_receives_the_digest_unless_told_otherwise(db_session: Session) -> None:
    user = User(email=f"digest-{uuid4().hex}@example.it", nome="Ada", ruolo="admin")
    db_session.add(user)
    db_session.flush()
    assert user.digest_settimanale is True


def test_one_digest_row_per_week(db_session: Session) -> None:
    db_session.add(
        Digest(settimana="2026-W38", inviato_a=["a@example.it"], occurred_at=datetime.now(UTC))
    )
    db_session.flush()
    db_session.add(
        Digest(settimana="2026-W38", inviato_a=["b@example.it"], occurred_at=datetime.now(UTC))
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
