"""drop the two-login surface: admin_users, admin_sessions, and the old identity columns

Revision ID: 0012
Revises: 0011

Migration B of the identity merge (REB-281, design record
docs/superpowers/specs/2026-09-17-one-hub-one-identity-design.md §3): the contract half
of the expand-then-contract pair 0011 started. Every column this migration drops has
had nothing writing it since 0011 landed (REB-278 repointed every writer and reader at
`users`/`user_id` in the same PR), so the drop loses no live data -- it only removes the
`freelancers`/`companies`/`admin_tokens`/`member_sessions`/`magic_link_tokens`/
`member_logins`/`guide_downloads` copies that duplicated what `users` already carries
under `user_id`, and the two admin-only tables `users` has fully replaced.

`member_sessions`/`member_logins` rename to `sessions`/`logins` here rather than in A,
because the old and new foreign key coexisted through the whole A-to-B window and a
table named for the FK it no longer solely served (`freelancer_id` beside `user_id`)
was already accurate enough to ship; the rename only pays for itself once
`freelancer_id` is gone and "member" would otherwise be the one word left implying a
table an admin's own session also lives in (the same rule `REB-207`-`REB-212`/`REB-214`
already applied to this codebase: an identifier that actively misleads gets renamed).

`downgrade()` recreates every dropped table and column empty, structure only: the rows
are gone, which is correct, since every one of them was already carried into `users` by
migration A. It exists so `alembic downgrade` does not error on a missing table or
column if something else in the chain needs to go further back than this migration --
it is not a way to undo a production drop, which the design record's own "restore from
backup" answer for 0011 covers already.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The four tables migration A gave a `user_id` column and loosened `freelancer_id` on:
# same shape, same order, so upgrade and downgrade can share it.
_FREELANCER_KEYED_TABLES = (
    "member_sessions",
    "magic_link_tokens",
    "member_logins",
    "guide_downloads",
)


def upgrade() -> None:
    op.drop_index("uq_freelancers_email_lower", table_name="freelancers")
    op.drop_column("freelancers", "linkedin_url")
    op.drop_column("freelancers", "email")
    op.drop_column("freelancers", "cognome")
    op.drop_column("freelancers", "nome")

    op.drop_column("companies", "email")
    op.drop_column("companies", "referente")

    op.drop_column("admin_tokens", "admin_id")

    for table in _FREELANCER_KEYED_TABLES:
        op.drop_column(table, "freelancer_id")
    op.rename_table("member_sessions", "sessions")
    op.rename_table("member_logins", "logins")
    # Postgres does not rename an index or a constraint along with its table: without
    # this, `compare_metadata` sees a real diff, `ix_member_sessions_user_id` where the
    # model now expects `ix_sessions_user_id`.
    op.execute("ALTER INDEX ix_member_sessions_user_id RENAME TO ix_sessions_user_id")
    op.execute("ALTER INDEX ix_member_logins_user_id RENAME TO ix_logins_user_id")
    op.drop_table("admin_sessions")
    op.drop_table("admin_users")


def downgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("attivo", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "uq_admin_users_email_lower", "admin_users", [sa.text("lower(email)")], unique=True
    )
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_admin_sessions_token_hash"),
    )
    op.create_index("ix_admin_sessions_user_id", "admin_sessions", ["user_id"])

    op.execute("ALTER INDEX ix_logins_user_id RENAME TO ix_member_logins_user_id")
    op.execute("ALTER INDEX ix_sessions_user_id RENAME TO ix_member_sessions_user_id")
    op.rename_table("logins", "member_logins")
    op.rename_table("sessions", "member_sessions")

    for table in _FREELANCER_KEYED_TABLES:
        op.add_column(
            table,
            sa.Column(
                "freelancer_id",
                sa.Uuid(),
                sa.ForeignKey("freelancers.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )

    op.add_column(
        "admin_tokens",
        sa.Column("admin_id", sa.Uuid(), sa.ForeignKey("admin_users.id"), nullable=True),
    )

    op.add_column("companies", sa.Column("referente", sa.String(length=120), nullable=True))
    op.add_column("companies", sa.Column("email", sa.String(length=320), nullable=True))

    op.add_column("freelancers", sa.Column("nome", sa.String(length=120), nullable=True))
    op.add_column("freelancers", sa.Column("cognome", sa.String(length=120), nullable=True))
    op.add_column("freelancers", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column("freelancers", sa.Column("linkedin_url", sa.String(length=300), nullable=True))
    op.create_index(
        "uq_freelancers_email_lower", "freelancers", [sa.text("lower(email)")], unique=True
    )
