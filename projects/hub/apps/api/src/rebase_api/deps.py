"""One engine per process, one session per request."""

import threading
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from rebase_core.admin import AdminRead, AdminService
from rebase_core.analytics import Tracker, tracker_from_settings
from rebase_core.config import Settings, get_settings
from rebase_core.db import create_engine_from_settings, session_factory
from rebase_core.http import HttpCall, urllib_call
from rebase_core.mail import EmailSender, sender_from_settings
from rebase_core.members import MemberService
from rebase_core.schemas import MeRead
from rebase_core.users import UserService

ADMIN_COOKIE = "orbiters_admin"
MEMBER_COOKIE = "orbiters_user"

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None
_lock = threading.Lock()


def _get_session_factory() -> sessionmaker[Session]:
    global _engine, _factory
    if _factory is None:
        with _lock:
            if _factory is None:
                _engine = create_engine_from_settings(get_settings())
                _factory = session_factory(_engine)
    return _factory


def get_session() -> Iterator[Session]:
    session = _get_session_factory()()
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_admin(request: Request, session: SessionDep, settings: SettingsDep) -> AdminRead:
    """A signed-in person whose role is admin. Until REB-281 a live `orbiters_admin`
    session is accepted too, so the SPA that still logs in with a password keeps
    working across this deploy: a signed-in non-admin is a real identity hitting the
    wrong door (403), nobody signed in at all is 401 (design record 2026-09-17 §4)."""
    users = UserService(session, settings)
    me = users.resolve_admin(request.cookies.get(MEMBER_COOKIE))
    if me is not None:
        return AdminRead.model_validate(me)
    legacy = AdminService(session, settings).resolve(request.cookies.get(ADMIN_COOKIE))
    if legacy is not None:
        # Migration A guarantees every active admin_users row became a users row,
        # matched by email; a brand-new password admin created between 278 and 279 is
        # the one gap this legacy branch cannot close (design record's own §4).
        matched = users.by_email(legacy.email)
        if matched is not None:
            return AdminRead.model_validate(matched)
    if users.resolve(request.cookies.get(MEMBER_COOKIE)) is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Serve il ruolo di amministratore")
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Autenticazione richiesta")


AdminDep = Annotated[AdminRead, Depends(get_admin)]


def get_me(request: Request, session: SessionDep, settings: SettingsDep) -> MeRead:
    """Whoever the cookie resolves to, member or admin: the one dependency every
    signed-in route may depend on."""
    user = UserService(session, settings).resolve(request.cookies.get(MEMBER_COOKIE))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Autenticazione richiesta")
    return MemberService(session).me_read(user.id)


MeDep = Annotated[MeRead, Depends(get_me)]


def get_sender(settings: SettingsDep) -> EmailSender | None:
    """`None` without a key: the route answers 503 and nothing pretends to send."""
    return sender_from_settings(settings)


SenderDep = Annotated[EmailSender | None, Depends(get_sender)]


def get_http_call() -> HttpCall:
    """The one HTTP seam, as a dependency so a test can hand a fake where production
    hands `urllib_call`: the registry of PigroCRM's spaces is read through it (ORB-142)."""
    return urllib_call


HttpCallDep = Annotated[HttpCall, Depends(get_http_call)]


def get_tracker(settings: SettingsDep) -> Tracker | None:
    """The server half of the wizard's analytics (REB-215): `None` without a key, so a
    route that has one schedules the event and a route that has none does nothing."""
    return tracker_from_settings(settings)


TrackerDep = Annotated[Tracker | None, Depends(get_tracker)]
