"""The admin area's API: the lists an admin reads, and the promote/demote pair.

One cookie, `orbiters_user`, the same one every signed-in person carries, resolved
against `sessions` on every request (`deps.get_admin`, checking `role == 'admin'`).
Everything under this router reads or moves rows other people wrote, or grants the role
to one more person (ORB-123); nothing here writes on an applicant's behalf. The one
thing it writes about a person is the card an admin drafts from a signup (ORB-155), and
that is signed by the admin and refused where the person has already spoken.

Since REB-278 `GET /admins` filters `users` on `role == 'admin'`, and the promote/demote
pair is the only way to grant or revoke it: REB-281 dropped the password login and the
create/update pair that posted one, once the SPA that still called them (REB-279)
stopped being their last caller.
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Query, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from rebase_api.deps import AdminDep, SenderDep, SessionDep, SettingsDep
from rebase_api.downloads import cv_response
from rebase_core.admin_tokens import AdminRead
from rebase_core.comments import CommentService
from rebase_core.companies import CompanyService
from rebase_core.freelancers import FreelancerService
from rebase_core.logins import LoginService
from rebase_core.mail import EmailSender, Mail
from rebase_core.models import NAME_MAX_LENGTH
from rebase_core.perks import PerkService
from rebase_core.schemas import (
    CommentCreate,
    CommentRead,
    CompanyList,
    CompanyRead,
    FreelancerDraft,
    FreelancerList,
    FreelancerRead,
    GuideStats,
    LoginStats,
    SignupList,
    StatusChange,
)
from rebase_core.service import SignupService
from rebase_core.users import UserService
from rebase_core.validation import SafeStr

router = APIRouter(prefix="/api/hub", tags=["hub-admin"])

_log = logging.getLogger(__name__)


def _send(sender: EmailSender, mail: Mail) -> None:
    """Runs after the response, same reasoning as `routers/members.py`'s own: a refusal
    is logged without the address or the key."""
    if not sender.send(mail):
        _log.warning("a promotion's magic link mail was refused by the provider")


# ---- the admins ------------------------------------------------------------------------
#
# Who reads this area, and the one form that grants or revokes the role (ORB-123,
# REB-279): typing an email promotes whatever `users` row already answers to it, or
# creates a bare one from `nome`/`cognome` when none exists yet. No deactivation and no
# deletion here, on purpose: the `attivo` flag exists and nothing in the area changes it
# yet, and demoting is fully reversible since nothing is deleted.


@router.get("/admins", response_model=list[AdminRead])
def list_admins(_: AdminDep, session: SessionDep, settings: SettingsDep) -> list[AdminRead]:
    return [AdminRead.model_validate(u) for u in UserService(session, settings).list_admins()]


class PromoteRequest(BaseModel):
    """`POST /admins/promote`'s body: an email, and `nome`/`cognome` for an address
    with no `users` row yet -- ignored, harmlessly, when one already exists."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    nome: SafeStr | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    cognome: SafeStr | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)


@router.post("/admins/promote", response_model=AdminRead)
def promote_admin(
    _: AdminDep,
    session: SessionDep,
    settings: SettingsDep,
    sender: SenderDep,
    background: BackgroundTasks,
    payload: PromoteRequest,
) -> AdminRead:
    """Promotes whatever `users` row already answers to this address with one click
    and no form; an address with none yet is created bare, no freelancer card invented
    for it (§1, Nav and Amministratori). A brand-new row gets the same magic link
    everyone else gets, since it has no other way in yet."""
    users = UserService(session, settings)
    user, created = users.promote(payload.email, payload.nome, payload.cognome)
    if created and sender is not None:
        mail = users.request_link(user.email)
        if mail is not None:
            background.add_task(_send, sender, mail)
    return AdminRead.model_validate(user)


@router.post("/admins/{user_id}/demote", response_model=AdminRead)
def demote_admin(
    _: AdminDep, session: SessionDep, settings: SettingsDep, user_id: UUID
) -> AdminRead:
    """Sets `role = 'member'`, fully reversible since nothing is deleted."""
    return AdminRead.model_validate(UserService(session, settings).demote(user_id))


# ---- the lists -------------------------------------------------------------------------

Limit = Annotated[int, Query(ge=1, le=500)]


@router.get("/freelancers", response_model=FreelancerList)
def list_freelancers(
    _: AdminDep, session: SessionDep, limit: Limit = 100, stato: str | None = None
) -> FreelancerList:
    return FreelancerService(session).list_recent(limit=limit, stato=stato)


@router.get("/freelancers/{freelancer_id}", response_model=FreelancerRead)
def get_freelancer(_: AdminDep, session: SessionDep, freelancer_id: UUID) -> FreelancerRead:
    return FreelancerService(session).get(freelancer_id)


@router.get("/freelancers/{freelancer_id}/cv")
def download_cv(_: AdminDep, session: SessionDep, freelancer_id: UUID) -> Response:
    cv = FreelancerService(session).cv(freelancer_id)
    return cv_response(cv)


@router.patch("/freelancers/{freelancer_id}", response_model=FreelancerRead)
def move_freelancer(
    _: AdminDep, session: SessionDep, freelancer_id: UUID, change: StatusChange
) -> FreelancerRead:
    return FreelancerService(session).set_status(freelancer_id, change)


@router.get("/companies", response_model=CompanyList)
def list_companies(
    _: AdminDep, session: SessionDep, limit: Limit = 100, stato: str | None = None
) -> CompanyList:
    return CompanyService(session).list_recent(limit=limit, stato=stato)


@router.get("/companies/{company_id}", response_model=CompanyRead)
def get_company(_: AdminDep, session: SessionDep, company_id: UUID) -> CompanyRead:
    return CompanyService(session).get(company_id)


@router.patch("/companies/{company_id}", response_model=CompanyRead)
def move_company(
    _: AdminDep, session: SessionDep, company_id: UUID, change: StatusChange
) -> CompanyRead:
    return CompanyService(session).set_status(company_id, change)


@router.get("/logins", response_model=LoginStats)
def login_stats(_: AdminDep, session: SessionDep) -> LoginStats:
    """Who entered the hub and when (ORB-158): every login through a magic link, the
    distinct members behind them, the last week, the latest by name. Written by
    `POST /auth/enter` and by nothing else."""
    return LoginService(session).stats()


@router.get("/perks/guida", response_model=GuideStats)
def guide_stats(_: AdminDep, session: SessionDep) -> GuideStats:
    """How the guide is doing (ORB-156): every download, the distinct members behind
    them, the last week, and the latest ones by name. Read-only; the rows are written by
    `GET /me/guida` and by nothing else."""
    return PerkService(session).guide_stats()


@router.get("/signups", response_model=SignupList)
def list_signups(_: AdminDep, session: SessionDep, limit: Limit = 100) -> SignupList:
    return SignupService(session).list_recent(limit=limit)


@router.post(
    "/signups/{signup_id}/scheda",
    response_model=FreelancerRead,
    status_code=status.HTTP_201_CREATED,
)
def draft_card_from_signup(
    admin: AdminDep, session: SessionDep, signup_id: UUID, payload: FreelancerDraft
) -> FreelancerRead:
    """The freelancer card an admin writes from what the public web says about a signup
    (ORB-155): incomplete until the person adds the CV, the rate and the rest from the
    member area. The comment naming the sources is signed by the admin the cookie
    resolves to. 404 for an unknown signup; 422 naming `email` when the person has
    already filled their card, which research never overwrites."""
    return FreelancerService(session).draft_from_signup(signup_id, payload, admin.nome)


# ---- comments --------------------------------------------------------------------------
#
# Append-only, on the same cookie as everything else here. The author is the admin the
# cookie resolves to: the body carries the text alone, so nobody can sign as somebody
# else. No PATCH and no DELETE on purpose: a thread is a record (ORB-59).


@router.get("/freelancers/{freelancer_id}/comments", response_model=list[CommentRead])
def list_freelancer_comments(
    _: AdminDep, session: SessionDep, freelancer_id: UUID
) -> list[CommentRead]:
    return CommentService(session).list("freelancer", freelancer_id)


@router.post(
    "/freelancers/{freelancer_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
)
def add_freelancer_comment(
    admin: AdminDep, session: SessionDep, freelancer_id: UUID, payload: CommentCreate
) -> CommentRead:
    return CommentService(session).add("freelancer", freelancer_id, payload.testo, admin.nome)


@router.get("/companies/{company_id}/comments", response_model=list[CommentRead])
def list_company_comments(_: AdminDep, session: SessionDep, company_id: UUID) -> list[CommentRead]:
    return CommentService(session).list("company", company_id)


@router.post(
    "/companies/{company_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
)
def add_company_comment(
    admin: AdminDep, session: SessionDep, company_id: UUID, payload: CommentCreate
) -> CommentRead:
    return CommentService(session).add("company", company_id, payload.testo, admin.nome)
