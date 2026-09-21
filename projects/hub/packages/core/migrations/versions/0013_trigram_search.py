"""pg_trgm and the trigram search indexes for talenti and companies

Revision ID: 0013
Revises: 0012

REB-285: the admin's talenti and companies lists gain a `q` search parameter, matched
with an escaped `ILIKE` and ordered by `pg_trgm` similarity among the rows that match
(`rebase_core.search`). Nine indexes, one per column `TalentiService`/`CompanyService`
search: `users.nome`/`cognome`/`email` (a card's identity, and a company's referente,
both live there since REB-281), `signups.nome`/`cognome`/`email` (a bare sign-up's own,
for the leads beside the cards), `freelancers.posizione`, `companies.nome_azienda` and
`companies.progetto`.

`CREATE EXTENSION` is deliberately not guarded by a capability check, the same
reasoning PigroCRM's own `0021_pg_trgm_search_indexes.py` states: migrations run at API
start-up, so on a managed Postgres whose allowlist forbids `pg_trgm` the deploy fails
loudly here rather than starting an application that scans every row in silence with
one index fewer.

`IF NOT EXISTS` on every statement, the convention this package's own AGENTS.md states
for anything that may run against the database PigroCRM's sidecar seeded in production
("the database was inherited"): a second `alembic upgrade head` against a copy where an
operator already built these by hand changes nothing. `CONCURRENTLY` is not used for
the same reason PigroCRM's migration gives: Alembic runs each migration inside a
transaction, and `CREATE INDEX CONCURRENTLY` cannot run inside one. None of these nine
columns is huge (a name, an email, a short free-text position, a company name, a
project description bounded by the wizard's own form) and none of the four tables is at
a size where a plain `CREATE INDEX`'s exclusive lock is anything other than brief; an
installation large enough for that to matter builds the indexes by hand out-of-band and
this migration finds them already there.

Safe on a database where `freelancers`, `companies`, `signups` and `users` already hold
real rows: every statement only adds an extension and nine indexes, never touches a row,
a column, or an existing index, and costs nothing to run twice.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (index name, table, column). Mirrors the `Index(...postgresql_ops=...)` declarations
# on the four models exactly (`models.py`) -- `test_migrations.py`'s
# `compare_metadata` is what keeps the two honest.
_TRGM_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_users_nome_trgm", "users", "nome"),
    ("ix_users_cognome_trgm", "users", "cognome"),
    ("ix_users_email_trgm", "users", "email"),
    ("ix_signups_nome_trgm", "signups", "nome"),
    ("ix_signups_cognome_trgm", "signups", "cognome"),
    ("ix_signups_email_trgm", "signups", "email"),
    ("ix_freelancers_posizione_trgm", "freelancers", "posizione"),
    ("ix_companies_nome_azienda_trgm", "companies", "nome_azienda"),
    ("ix_companies_progetto_trgm", "companies", "progetto"),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, table, column in _TRGM_INDEXES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING gin ({column} gin_trgm_ops)"
        )


def downgrade() -> None:
    for name, _table, _column in reversed(_TRGM_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {name}")
    # The extension is left installed, the same choice PigroCRM's 0021 makes: dropping
    # it would fail if anything else in the database came to depend on it, and an
    # extension costs nothing to leave behind.
