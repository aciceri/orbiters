"""trigram search index for the admin tokens list

Revision ID: 0014
Revises: 0013

REB-313: Amministratori, Agenti and Accessi gain a `q` search parameter beside Talenti
and Aziende (0013). Amministratori and Accessi search the `users` columns 0013 already
indexed (`nome`/`cognome`/`email`); Agenti's tokens have no linked `users` row to
search instead, so this migration adds the one trigram index REB-313 needs that 0013
did not already cover: `admin_tokens.nome`, the name an admin gave their own token.

Same conventions as 0013: `CREATE EXTENSION` unguarded (already installed by 0013, but
this migration stands alone against a database that adopted this table before it),
`IF NOT EXISTS` on every statement, no `CONCURRENTLY` since Alembic runs inside a
transaction and a personal-token table is never large enough for a plain `CREATE INDEX`
to matter.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_admin_tokens_nome_trgm"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_INDEX_NAME} ON admin_tokens USING gin (nome gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX_NAME}")
