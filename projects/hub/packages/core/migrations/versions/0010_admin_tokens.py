"""admin_tokens: a personal token per admin, for an agent

Revision ID: 0010
Revises: 0009

One new table (REB-213): the credential the MCP server takes as a bearer. The shape of
the CRM's `personal_access_tokens`, on `admin_users` instead of `users`: the hash of the
value, its visible prefix, when it was last presented and when it was revoked.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("admin_id", sa.Uuid(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("prefix", sa.String(length=20), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_admin_tokens_admin_id", "admin_tokens", ["admin_id"])


def downgrade() -> None:
    op.drop_index("ix_admin_tokens_admin_id", table_name="admin_tokens")
    op.drop_table("admin_tokens")
