from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rebase_core.db import Base, PrimaryKeyMixin, TimestampMixin

UTM_MAX_LENGTH = 200
UTM_COLUMNS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "utm_id")
NAME_MAX_LENGTH = 120
LINKEDIN_URL_MAX_LENGTH = 300

# Every column added after the production table already existed, with the width each
# one needs. Migration 0001 adopts that table as it stands and adds these with
# `ADD COLUMN IF NOT EXISTS`, which is how the rows PigroCRM's sidecar collected keep
# their place. The UTM six arrived on 2026-09-08, `nome`/`cognome`/`linkedin_url` right
# after; the tuple stays because `test_migrations.py` proves the adoption against a
# table that predates all of them.
LATE_COLUMNS: tuple[tuple[str, int], ...] = (
    *((column, UTM_MAX_LENGTH) for column in UTM_COLUMNS),
    ("nome", NAME_MAX_LENGTH),
    ("cognome", NAME_MAX_LENGTH),
    ("linkedin_url", LINKEDIN_URL_MAX_LENGTH),
)


class Signup(Base, PrimaryKeyMixin):
    __tablename__ = "signups"

    # Same width and the same case-insensitive uniqueness as `users.email`: the
    # service lowers the address before writing, and the functional index is what
    # makes that a database fact rather than an app-level habit.
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Where the signup came from, as the URL said it: the five standard UTM keys plus
    # `utm_id`, which LinkedIn fills with the ad set. All optional, all written once --
    # the first attribution of an address is the one that stays (see `SignupService`).
    # Added to a table that already existed in production: migration 0001 adds them.
    utm_source: Mapped[str | None] = mapped_column(String(UTM_MAX_LENGTH), default=None)
    utm_medium: Mapped[str | None] = mapped_column(String(UTM_MAX_LENGTH), default=None)
    utm_campaign: Mapped[str | None] = mapped_column(String(UTM_MAX_LENGTH), default=None)
    utm_content: Mapped[str | None] = mapped_column(String(UTM_MAX_LENGTH), default=None)
    utm_term: Mapped[str | None] = mapped_column(String(UTM_MAX_LENGTH), default=None)
    utm_id: Mapped[str | None] = mapped_column(String(UTM_MAX_LENGTH), default=None)
    # Who they are. `SignupCreate` requires both, so nothing written from today on is
    # nameless -- but the twenty-four rows the form collected when it asked only for an
    # address have no name to give, so the columns stay nullable rather than being
    # backfilled with `''`, which would claim a name was recorded and found empty.
    # An empty column is filled in the next time that address signs up (`SignupService`).
    nome: Mapped[str | None] = mapped_column(String(NAME_MAX_LENGTH), default=None)
    cognome: Mapped[str | None] = mapped_column(String(NAME_MAX_LENGTH), default=None)
    # Optional for everyone, always: a freelance with no LinkedIn is still a freelance.
    linkedin_url: Mapped[str | None] = mapped_column(String(LINKEDIN_URL_MAX_LENGTH), default=None)

    __table_args__ = (Index("uq_orbiters_signups_email_lower", func.lower(email), unique=True),)


# ---- identity: one row per person, whatever they are to the hub ------------------------

USER_ROLES = ("member", "admin")


class User(Base, PrimaryKeyMixin, TimestampMixin):
    """One row per person the hub has an address for, one per `lower(email)`
    (`uq_users_email_lower`). A freelancer card, a company's own request and an admin
    grant are things a `users` row may have, zero or more of each, not three values
    competing for one row's identity (design record 2026-09-17, decision (c)): Lorenzo
    and Ivan are freelancers on some engagements, a company's own referente on others,
    and admins throughout. `role` is `member` or `admin` (`USER_ROLES`), validated in
    the service layer the way `stato` and `compilata_da` already are -- two values on a
    handful of rows do not buy a `user_roles` table. `attivo`, carried over from
    `admin_users.attivo` by REB-278's migration, still means only "this admin's tokens
    and sessions keep failing the same way": nothing deactivates a member yet, matching
    today."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    nome: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    cognome: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    linkedin_url: Mapped[str | None] = mapped_column(String(LINKEDIN_URL_MAX_LENGTH), default=None)
    role: Mapped[str] = mapped_column(String(10), nullable=False, default="member")
    attivo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (Index("uq_users_email_lower", func.lower(email), unique=True),)


# ---- the hub proper: who wants to work, and who needs people --------------------------

FREELANCER_STATES = ("nuovo", "contattato", "attivo", "scartato")
# Who wrote the seven answers last (ORB-155): the person, through the wizard or the
# member area, or an admin, from what the public web says about a signup. Research never
# overwrites `persona`; the person's own words win.
COMPILATA_DA = ("persona", "admin")
COMPANY_STATES = ("nuovo", "contattato", "in_corso", "chiuso")
REMOTE_OPTIONS = ("remoto", "ibrido", "in_sede")
POSIZIONE_MAX_LENGTH = 160
AZIENDA_MAX_LENGTH = 200
DURATA_MAX_LENGTH = 120
CV_FILENAME_MAX_LENGTH = 255
CV_MIME_MAX_LENGTH = 100
# Five megabytes: a CV is two pages, and the largest a designer's portfolio-as-CV gets
# before it stops being a CV. Enforced in the service on the bytes themselves, so the
# API and the MCP server cannot disagree about it.
CV_MAX_BYTES = 5 * 1024 * 1024


ORIGINE_MAX_LENGTH = 40


class UtmMixin:
    """Where a submission came from, as the page's URL said it. Optional, written once.
    `origine` is the page of the site the person started from (`home`, `pigrocrm`), which
    the landing's script puts on every door into the hub as `da=` (ORB-167): the campaign
    says which ad, this says which page."""

    origine: Mapped[str | None] = mapped_column(String(ORIGINE_MAX_LENGTH), default=None)

    utm_source: Mapped[str | None] = mapped_column(String(UTM_MAX_LENGTH), default=None)
    utm_medium: Mapped[str | None] = mapped_column(String(UTM_MAX_LENGTH), default=None)
    utm_campaign: Mapped[str | None] = mapped_column(String(UTM_MAX_LENGTH), default=None)
    utm_content: Mapped[str | None] = mapped_column(String(UTM_MAX_LENGTH), default=None)
    utm_term: Mapped[str | None] = mapped_column(String(UTM_MAX_LENGTH), default=None)
    utm_id: Mapped[str | None] = mapped_column(String(UTM_MAX_LENGTH), default=None)


class Freelancer(Base, PrimaryKeyMixin, TimestampMixin, UtmMixin):
    """A person who filled in the hub's wizard: who they are, what they do, what they
    cost, and their CV -- in the row, as bytes. In the database rather than on a disk or
    a Drive because a CV is personal data with a retention to honour, and one place to
    delete from is one place (hub spec, 2026-09-09; Ivan's decision).

    One row per address (`uq_freelancers_email_lower`): a person who submits twice has
    corrected their application, and the second submission updates the first. `stato`
    and `note` are the admin's, never the applicant's.

    Since ORB-155 a card can also be born from a signup, with what an admin found on
    the public web: a name, a LinkedIn profile, a position, some links. The CV, the rate,
    the position and the remote option are therefore nullable -- nothing public states
    them -- and the person completes the card from the member area. `compilata_da` says
    who wrote the answers last, so research can tell a card it may replace from one it
    may not. Migration 0007 loosened the columns; the wizard still requires all of them.

    Since REB-278 the identity is `users`, one row per person: `user_id` is `NOT NULL
    UNIQUE`, at most one card per person, and `FreelancerService` keeps `nome`/`cognome`/
    `email`/`linkedin_url` here in step with the linked `users` row on every write that
    legitimately changes them (a first application, a member's own edit, an admin's
    re-drafted research) rather than a second, independently drifting copy."""

    __tablename__ = "freelancers"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    nome: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    cognome: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    linkedin_url: Mapped[str | None] = mapped_column(String(LINKEDIN_URL_MAX_LENGTH), default=None)
    cv_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    cv_filename: Mapped[str | None] = mapped_column(String(CV_FILENAME_MAX_LENGTH), default=None)
    cv_mime: Mapped[str | None] = mapped_column(String(CV_MIME_MAX_LENGTH), default=None)
    cv_size: Mapped[int | None] = mapped_column(Integer, default=None)
    tariffa_giornaliera: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=None)
    posizione: Mapped[str | None] = mapped_column(String(POSIZIONE_MAX_LENGTH), default=None)
    remoto: Mapped[str | None] = mapped_column(String(10), default=None)
    links: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    stato: Mapped[str] = mapped_column(String(20), nullable=False, default="nuovo")
    note: Mapped[str | None] = mapped_column(Text, default=None)
    compilata_da: Mapped[str] = mapped_column(String(10), nullable=False, default="persona")

    __table_args__ = (
        Index("uq_freelancers_email_lower", func.lower(email), unique=True),
        Index("ix_freelancers_created_at", "created_at"),
        Index("uq_freelancers_user_id", "user_id", unique=True),
    )


class Company(Base, PrimaryKeyMixin, TimestampMixin, UtmMixin):
    """A company that needs people: the project in a few lines, from when and for how
    long, and what a day is worth to them. Several rows per company are fine -- a company
    has several projects -- so nothing is unique here but the id.

    Since REB-278 `user_id` points at the referente's `users` row, not unique -- a
    person files several requests over time -- and `CompanyService` keeps `referente`/
    `email` here in step with it at the moment each request is written, the same
    reasoning as `Freelancer.user_id`."""

    __tablename__ = "companies"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    nome_azienda: Mapped[str] = mapped_column(String(AZIENDA_MAX_LENGTH), nullable=False)
    referente: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    progetto: Mapped[str] = mapped_column(Text, nullable=False)
    periodo_da: Mapped[date] = mapped_column(Date, nullable=False)
    durata: Mapped[str] = mapped_column(String(DURATA_MAX_LENGTH), nullable=False)
    budget_giornaliero: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    stato: Mapped[str] = mapped_column(String(20), nullable=False, default="nuovo")
    note: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (Index("ix_companies_created_at", "created_at"),)


# ---- comments: what an admin or an assistant says about a row, over time ---------------

COMMENT_ENTITY_TYPES = ("freelancer", "company")
COMMENT_MAX_LENGTH = 4000
AUTORE_MAX_LENGTH = NAME_MAX_LENGTH


class Comment(Base, PrimaryKeyMixin):
    """One remark about a freelancer or a company, signed and dated. Append-only, like
    PigroCRM's timeline entries: no update and no delete anywhere in the hub, so a
    thread read in a month is the thread as it was written. `note` on the row itself
    stays the one-line summary an admin overwrites; this is the history beside it
    (ORB-59, Ivan's decision of 2026-09-09).

    `entity_type` plus `entity_id` rather than two nullable foreign keys: the service
    checks the row exists before writing, and one table with one index is what a
    thread on a third kind of row would reuse without a migration on this table."""

    __tablename__ = "comments"

    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(nullable=False)
    testo: Mapped[str] = mapped_column(Text, nullable=False)
    autore: Mapped[str] = mapped_column(String(AUTORE_MAX_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_comments_entity", "entity_type", "entity_id", "created_at"),)


# ---- the admin area -------------------------------------------------------------------

ADMIN_SESSION_TOKEN_HASH_LENGTH = 64  # sha256, hex


class AdminUser(Base, PrimaryKeyMixin, TimestampMixin):
    """Whoever reads the hub's admin area. Created by `rebase createadmin` or, since
    ORB-123, by another admin from «Amministratori»; never by a public form: the hub has
    no public account, only applicants and the people who read them."""

    __tablename__ = "admin_users"

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    nome: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    attivo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (Index("uq_admin_users_email_lower", func.lower(email), unique=True),)


ADMIN_TOKEN_PREFIX_LENGTH = 20


class AdminToken(Base, PrimaryKeyMixin, TimestampMixin):
    """A personal token of an admin, for an agent (REB-213): the credential the MCP
    server takes as a bearer. Only the sha256 of the value is stored; the value itself
    is shown once, at creation, and never again. `prefix` is the visible head of it, so a
    list can tell two tokens apart. No expiry: `revoked_at` is the end of a token, and a
    revoked one is refused like an unknown one. Hangs on the admin with a plain foreign
    key, as the sessions do: an admin is never deleted, only deactivated, and a
    deactivated admin's tokens stop resolving with them.

    Since REB-278 `user_id` is the owner (`users.id`, `role == 'admin'`); `admin_id`
    stays, read and written by nothing from this PR on, because a token minted after
    this deploy may belong to an admin promoted with no `admin_users` row at all.
    Migration B drops it once nothing points at it any more."""

    __tablename__ = "admin_tokens"

    admin_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admin_users.id"), default=None, index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    token_hash: Mapped[str] = mapped_column(
        String(ADMIN_SESSION_TOKEN_HASH_LENGTH), nullable=False, unique=True
    )
    prefix: Mapped[str] = mapped_column(String(ADMIN_TOKEN_PREFIX_LENGTH), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class AdminSession(Base, PrimaryKeyMixin):
    """One opaque cookie, stored hashed, sliding expiry. Not a JWT pair: the admin area is
    a handful of people reading a handful of lists, and a database lookup per request is
    cheaper than a second token, a rotation and a grace window to reason about. Revoking
    is deleting the row, which a logout does."""

    __tablename__ = "admin_sessions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("admin_users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(
        String(ADMIN_SESSION_TOKEN_HASH_LENGTH), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---- the member area: how a freelancer gets back in ------------------------------------

TOKEN_HASH_LENGTH = 64  # sha256, hex


class MagicLinkToken(Base, PrimaryKeyMixin):
    """One link, one entry. The raw value travels in the mail and nowhere else; the row
    holds its sha256, a deadline (`magic_link_minutes`) and the moment it was spent, so a
    link forwarded or fetched twice opens nothing the second time. Hangs on the person
    with `ON DELETE CASCADE`: deleting them deletes their way in.

    Since REB-278 the link is for anyone with a `users` row, not only a freelancer:
    `user_id` is the owner and `freelancer_id` -- kept for the rows already there,
    written by nothing from this PR on -- can no longer be `NOT NULL`: an admin with
    no card, or a company's own referente, has none to give it."""

    __tablename__ = "magic_link_tokens"

    freelancer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("freelancers.id", ondelete="CASCADE"), default=None, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class MemberLogin(Base, PrimaryKeyMixin):
    """One row per time somebody entered through a magic link (ORB-158): who and when,
    and nothing else -- no address, no user agent. A log rather than the session table,
    which forgets a session on logout and on expiry, so the admin can read who came in
    and when a week later. Written by `UserService.enter` in the commit that opens the
    session. Hangs on the person with `ON DELETE CASCADE`, like the sessions.

    Since REB-278 `user_id` is the owner, for anyone who signs in, not only a
    freelancer; `freelancer_id`, kept for the rows already there, can no longer be
    `NOT NULL` for the same reason as `magic_link_tokens.freelancer_id`."""

    __tablename__ = "member_logins"

    freelancer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("freelancers.id", ondelete="CASCADE"), default=None, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GuideDownload(Base, PrimaryKeyMixin):
    """One row per time somebody fetched the guide (ORB-156): who and when, and nothing
    else. A log rather than a counter on the freelancer, so the admin can read a trend
    and see who came back for it; nothing about the file itself is stored, since the
    file is package data and the same for everybody. Hangs on the person with
    `ON DELETE CASCADE`: a deleted person takes their downloads.

    Since REB-278 `user_id` is the owner; `freelancer_id`, kept for the rows already
    there, can no longer be `NOT NULL` for the same reason as the sessions'."""

    __tablename__ = "guide_downloads"

    freelancer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("freelancers.id", ondelete="CASCADE"), default=None, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MemberSession(Base, PrimaryKeyMixin):
    """The session's shape: opaque cookie, hashed at rest, sliding expiry, revoked by
    deleting the row. One table and one cookie for everyone who signs in, member and
    admin alike (REB-278): a role is read off the `users` row it resolves to, not off
    which table the session lives in.

    `user_id` is the owner, for anyone; `freelancer_id`, kept for the rows already
    there, can no longer be `NOT NULL` for the same reason as the other three tables
    the magic link touches: an admin with no card has nothing to put in it."""

    __tablename__ = "member_sessions"

    freelancer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("freelancers.id", ondelete="CASCADE"), default=None, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
