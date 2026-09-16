"""a user can switch the weekly report off, and a digests table remembers each week sent

Revision ID: 0035
Revises: 0034

Spec 2026-09-16 §3.3. `users.digest_settimanale` decides whether the weekly report
reaches a person; on by default, so the mail itself carries the switch off rather than
an empty inbox being the only signal it exists.

`digests` holds one row per week the report went out: `settimana` (`YYYY-Www`, unique)
makes the send idempotent across a cron that runs twice or two hosts, `inviato_a` keeps
the addresses that received it, and `occurred_at` when. Nothing sends yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("digest_settimanale", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "digests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("settimana", sa.String(length=8), nullable=False),
        sa.Column("inviato_a", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("settimana", name="uq_digests_settimana"),
    )


def downgrade() -> None:
    op.drop_table("digests")
    op.drop_column("users", "digest_settimanale")
