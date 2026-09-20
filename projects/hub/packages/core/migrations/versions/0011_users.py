"""users: one identity per person, and everything that means the person repointed at it

Revision ID: 0011
Revises: 0010

Migration A of the identity merge (REB-278, design record
docs/superpowers/specs/2026-09-17-one-hub-one-identity-design.md §3): a new `users`
table, one row per person, backfilled from every existing source of a name and an
address -- `freelancers`, then `admin_users`, then `companies.referente` -- and a
`user_id` foreign key added everywhere the person is what today's `freelancer_id` or
`admin_id` means. Expand only: nothing here drops or renames a column or a table, and
`admin_users`/`admin_sessions` are read for the backfill and otherwise left alone, since
the SPA keeps logging admins in with them until REB-279 moves off `/auth/login`.

Beyond the SQL the design record spells out, this migration also loosens five legacy
foreign keys that would otherwise block the very rows the unified magic link needs to
write from the day this lands: `admin_tokens.admin_id` and the `freelancer_id` on
`member_sessions`, `magic_link_tokens`, `member_logins` and `guide_downloads` were
`NOT NULL` against a table that only ever held a freelancer or a password admin. Once
`/auth/link` and `/auth/enter` open a session for *any* `users` row (a company's own
referente, or an admin with no freelancer card, same as one with a card), a session, a
magic link, a login or a download for a person with no freelancer row -- or a token for
an admin promoted with no `admin_users` row -- has nothing to put in that column and can
only carry `user_id`. Loosening a `NOT NULL` adds nothing that was not already there and
drops nothing, so it stays inside migration A's own "expand, additive" rule.

A fresh database has no rows in `freelancers`, `admin_users` or `companies` yet, so the
backfill runs over nothing; `downgrade()` refuses regardless, because a database that
has taken real traffic since this ran cannot be walked back with a `DROP COLUMN` this
file could honestly call safe -- that is a restore from backup, per the design record.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The four tables the magic link and its logs touch, all shaped the same way: gain
# `user_id`, backfill it from the freelancer the row already names, then loosen
# `freelancer_id` because a future row may belong to someone with no freelancer card.
_FREELANCER_KEYED_TABLES = (
    "member_sessions",
    "magic_link_tokens",
    "member_logins",
    "guide_downloads",
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("cognome", sa.String(length=120), nullable=False),
        sa.Column("linkedin_url", sa.String(length=300), nullable=True),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("attivo", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    # 1. Every freelancer is a user; the card already wrote both names.
    op.execute(
        """
        INSERT INTO users
            (id, email, nome, cognome, linkedin_url, role, attivo, created_at, updated_at)
        SELECT gen_random_uuid(), lower(f.email), f.nome, f.cognome, f.linkedin_url,
               'member', true, f.created_at, f.updated_at
        FROM freelancers f
        """
    )

    # 2. Every admin, active or not, who is not already a user from step 1: `au.nome` is
    #    one field, not two, so `cognome` is left blank on purpose -- fixed by hand once,
    #    after this deploy, against the real data (design record decision (d)).
    op.execute(
        """
        INSERT INTO users (id, email, nome, cognome, role, attivo, created_at, updated_at)
        SELECT gen_random_uuid(), lower(au.email), au.nome, '', 'admin', au.attivo,
               au.created_at, au.updated_at
        FROM admin_users au
        WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.email = lower(au.email))
        """
    )
    # Promote whoever already got a row from step 1 and is also an active admin. A
    # deactivated admin who is also a freelancer stays 'member' and attivo=true:
    # `attivo` is the person's own flag now, and nothing deactivates a freelancer today.
    op.execute(
        """
        UPDATE users u SET role = 'admin'
        FROM admin_users au
        WHERE u.email = lower(au.email) AND au.attivo
        """
    )

    # 3. Every company referente with no row from steps 1-2: the request is the only
    #    trace of that address, `cognome` blank for the same reason as step 2. A
    #    repeated referente across several requests from the same address picks one
    #    arbitrarily (`DISTINCT ON`, oldest request).
    op.execute(
        """
        INSERT INTO users (id, email, nome, cognome, role, attivo, created_at, updated_at)
        SELECT DISTINCT ON (lower(c.email))
               gen_random_uuid(), lower(c.email), c.referente, '', 'member', true,
               c.created_at, c.created_at
        FROM companies c
        WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.email = lower(c.email))
        ORDER BY lower(c.email), c.created_at
        """
    )

    op.add_column(
        "freelancers", sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True)
    )
    op.execute(
        "UPDATE freelancers f SET user_id = u.id FROM users u WHERE u.email = lower(f.email)"
    )
    op.alter_column("freelancers", "user_id", nullable=False)
    op.create_index("uq_freelancers_user_id", "freelancers", ["user_id"], unique=True)

    op.add_column(
        "companies", sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True)
    )
    op.execute("UPDATE companies c SET user_id = u.id FROM users u WHERE u.email = lower(c.email)")
    op.alter_column("companies", "user_id", nullable=False)
    op.create_index("ix_companies_user_id", "companies", ["user_id"])

    op.add_column(
        "admin_tokens", sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True)
    )
    op.execute(
        """
        UPDATE admin_tokens t SET user_id = u.id
        FROM admin_users au JOIN users u ON u.email = lower(au.email)
        WHERE t.admin_id = au.id
        """
    )
    # A token whose owner matched no user cannot happen after steps 1-2 above (every
    # admin_users row becomes a users row), but the statement stays: `NULL` here would
    # abort the `NOT NULL` below, which inside the API image's `CMD` is a crash loop,
    # and a defensive `DELETE` costs one line against a table that must never grow this way.
    op.execute("DELETE FROM admin_tokens WHERE user_id IS NULL")
    op.alter_column("admin_tokens", "user_id", nullable=False)
    op.create_index("ix_admin_tokens_user_id", "admin_tokens", ["user_id"])
    # `admin_id` stays, read by nothing from this PR on: a token minted after this
    # deploy may belong to an admin promoted through the new promote/demote pair, with
    # no `admin_users` row at all, so the column that used to require one cannot stay
    # `NOT NULL`.
    op.alter_column("admin_tokens", "admin_id", nullable=True)

    for table in _FREELANCER_KEYED_TABLES:
        op.add_column(
            table,
            sa.Column(
                "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
            ),
        )
        op.execute(
            f"UPDATE {table} s SET user_id = f.user_id "
            f"FROM freelancers f WHERE s.freelancer_id = f.id"
        )
        op.alter_column(table, "user_id", nullable=False)
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
        # Same reasoning as `admin_tokens.admin_id`: from now on a row here may belong
        # to a person with no freelancer card at all (a bare admin, a company's own
        # referente signing in through the same magic link), so the column that used
        # to be every row's only owner can no longer demand one.
        op.alter_column(table, "freelancer_id", nullable=True)


def downgrade() -> None:
    raise RuntimeError(
        "0011 does not downgrade: once a session, a token, a login or a download "
        "exists that carries only user_id, undoing this migration is a restore from "
        "backup, not a DROP COLUMN this file can pretend is safe."
    )
