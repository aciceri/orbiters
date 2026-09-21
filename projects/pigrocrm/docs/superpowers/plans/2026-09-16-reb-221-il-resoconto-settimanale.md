# The weekly report (`pigrocrm digest`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every Monday at 8 each space with data receives one mail that reports its week: money to collect, money to issue, invoices issued and collected, hours, pipeline, the three signals; sent once per space and week by a CLI command run from cron.

**Architecture:** A new core module `pigrocrm/core/digest/` composes existing repositories and services into a pure `WeeklyDigest` schema; `mail.py` renders it; a `DigestRun` sends it to the space's opted-in users, records a `digests` row (idempotency per ISO week), an activity and a PostHog server event; `cli.py` gets a `digest` subcommand that walks the tenant registry exactly as `ensure-space-defaults` does. No worker, no queue: cron calls the command.

**Tech Stack:** Python 3.13, SQLAlchemy 2, Alembic, Pydantic 2, FastAPI (one field), Resend through the existing `EmailSender` seam, `posthog` Python SDK 7.53.0, pytest with testcontainers Postgres. Web: one switch in the settings (React, Vitest).

**Spec:** `projects/pigrocrm/docs/superpowers/specs/2026-09-16-la-settimana-e-la-home-design.md` § 3 (read it first; §3.1 is the exact content of the mail).

## Global Constraints

- Run everything from the repository root of the worktree: `uv run pytest -q projects/pigrocrm/packages/core/tests/<file>` and `uv run ruff check projects/pigrocrm && uv run ruff format projects/pigrocrm && uv run mypy` before every commit. Pandoc and Typst are on PATH here; Docker is running (testcontainers).
- `packages/core` imports neither adapter; a new runtime dependency must be added to `[project].dependencies` in `projects/pigrocrm/packages/core/pyproject.toml` (then `uv lock` and `uv sync --frozen`), or `tests/test_architecture.py` fails.
- Never `date.today()` / `datetime.now()` in core: use `pigrocrm.core.db.clock` (`today_local`, `current_week`); `tests/test_clock.py` enforces it by AST.
- `pigrocrm/core/dashboard/` may contain no arithmetic; the digest lives in `pigrocrm/core/digest/`, and `DashboardService` is imported from `pigrocrm.core.dashboard.service` (not exported by the package on purpose). Its `get_operational_dashboard` needs a session **with no transaction open**: call it before any other read in the same session.
- Copy in Italian for everything a person reads (mail, CLI lines); code, comments, docstrings, commit messages in English, first person, Conventional Commits, no AI trailer, last line of the body `REB-221.`. Commit with a pathspec, never `git add -A`.
- `ActivityService.record(...)` flushes and never commits; it must be the last session touch before the caller's `commit()`. Payloads carry counts, never amounts, names or addresses.
- Every value from outside in the HTML mail goes through `html.escape`; amounts are rendered `1.800,00 €` and dates `lun 8 set`.

---

### Task 1: The schema: `users.digest_settimanale` and the `digests` table (migration 0035)

**Files:**
- Modify: `projects/pigrocrm/packages/core/src/pigrocrm/core/auth/models.py` (class `User`, after `attivo`)
- Create: `projects/pigrocrm/packages/core/src/pigrocrm/core/digest/__init__.py`, `projects/pigrocrm/packages/core/src/pigrocrm/core/digest/models.py`
- Modify: `projects/pigrocrm/packages/core/src/pigrocrm/core/models_registry.py` (append the import)
- Create: `projects/pigrocrm/packages/core/migrations/versions/0035_digest_settimanale.py`
- Modify: `projects/pigrocrm/packages/core/src/pigrocrm/core/auth/schemas.py` (`UserRead`, `UserUpdate`)
- Test: `projects/pigrocrm/packages/core/tests/test_digest_models.py` (new); `tests/test_migrations.py` already asserts models and migrations agree.

**Interfaces:**
- Produces: `User.digest_settimanale: Mapped[bool]` (default `True`); `Digest` model, table `digests` with `id` (UUID PK from `PrimaryKeyMixin`), `settimana: Mapped[str]` (`String(8)`, e.g. `2026-W38`, unique), `inviato_a: Mapped[list[str]]` (JSONB), `occurred_at: Mapped[datetime]` (timezone-aware, default now); `UserRead.digest_settimanale: bool`, `UserUpdate.digest_settimanale: bool | None = None`.

- [ ] **Step 1: Write the failing test**

```python
# projects/pigrocrm/packages/core/tests/test_digest_models.py
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
    db_session.add(Digest(settimana="2026-W38", inviato_a=["a@example.it"], occurred_at=datetime.now(UTC)))
    db_session.flush()
    db_session.add(Digest(settimana="2026-W38", inviato_a=["b@example.it"], occurred_at=datetime.now(UTC)))
    with pytest.raises(IntegrityError):
        db_session.flush()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest -q projects/pigrocrm/packages/core/tests/test_digest_models.py`
Expected: FAIL with `ModuleNotFoundError: pigrocrm.core.digest`

- [ ] **Step 3: Write the models, the registry line, the schema fields and the migration**

`auth/models.py`, inside `User` right after `attivo`:

```python
    # Whether the weekly report reaches this person (spec 2026-09-16 §3.3). On by
    # default: the report is the reason to come back, and the mail carries the switch.
    digest_settimanale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

`digest/__init__.py`:

```python
"""The weekly report of a space: composed from the registers, rendered as one mail,
sent once per week (spec 2026-09-16 §3)."""
```

`digest/models.py`:

```python
"""One row per week the report went out (spec 2026-09-16 §3.3).

`settimana` is the ISO week (`2026-W38`) and it is unique: a cron that runs twice, or
two hosts, cannot send the same week twice. `inviato_a` keeps the addresses that
received it, which is what a person asking «did I get it?» needs answered.
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pigrocrm.core.db.base import Base, PrimaryKeyMixin


class Digest(Base, PrimaryKeyMixin):
    __tablename__ = "digests"

    settimana: Mapped[str] = mapped_column(String(8), nullable=False, unique=True)
    inviato_a: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

(Check `pigrocrm/core/db/base.py` for the exact names of `Base` and `PrimaryKeyMixin`; `Activity` in `activities/models.py` is the model to copy for JSONB and timezone columns.)

`models_registry.py`: add `from pigrocrm.core.digest.models import Digest  # noqa: F401` in alphabetical position.

`auth/schemas.py`: `UserUpdate` gains `digest_settimanale: bool | None = None`; `UserRead` gains `digest_settimanale: bool` after `attivo`. Check `UserService.update` in `auth/service.py` applies every non-`None` field of `UserUpdate` generically; if it lists fields by name, add this one.

Migration `0035_digest_settimanale.py`, docstring in the house style, then:

```python
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
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("settimana", sa.String(length=8), nullable=False),
        sa.Column("inviato_a", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("settimana", name="uq_digests_settimana"),
    )


def downgrade() -> None:
    op.drop_table("digests")
    op.drop_column("users", "digest_settimanale")
```

Match the `id` column type and any `created_at`/`updated_at` columns to what `PrimaryKeyMixin` declares (read migration `0034` and `Base` first; `test_migrations_produce_exactly_the_models_schema` compares the two and will name any difference).

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q projects/pigrocrm/packages/core/tests/test_digest_models.py projects/pigrocrm/packages/core/tests/test_migrations.py projects/pigrocrm/packages/core/tests/test_auth.py`
Expected: PASS (if an auth test snapshots `UserRead` fields, extend it with `digest_settimanale: True`).

- [ ] **Step 5: Lint, types, commit**

```bash
uv run ruff format projects/pigrocrm && uv run ruff check projects/pigrocrm && uv run mypy
git add projects/pigrocrm/packages/core/src/pigrocrm/core/auth/models.py projects/pigrocrm/packages/core/src/pigrocrm/core/auth/schemas.py projects/pigrocrm/packages/core/src/pigrocrm/core/digest projects/pigrocrm/packages/core/src/pigrocrm/core/models_registry.py projects/pigrocrm/packages/core/migrations/versions/0035_digest_settimanale.py projects/pigrocrm/packages/core/tests/test_digest_models.py
git commit -m "feat(core): a user can switch the weekly report off, and a digests table remembers each week sent

Migration 0035: users.digest_settimanale (default true) and digests(settimana unique,
inviato_a, occurred_at), the two things the weekly report needs before any of it can
run (spec 2026-09-16 §3.3). Nothing sends yet.

REB-221."
```

---

### Task 2: The invoice reads the week needs

**Files:**
- Modify: `projects/pigrocrm/packages/core/src/pigrocrm/core/invoices/repository.py` (`InvoiceRepository`, next to `sum_scaduto` and `count_emesse_in_periodo`)
- Test: `projects/pigrocrm/packages/core/tests/test_invoice_aggregates.py` (append)

**Interfaces:**
- Produces, on `InvoiceRepository`:
  - `list_emesse_in_periodo(da: date, a: date) -> list[Invoice]` (issued filter, `data_emissione` between `da` and `a` inclusive, ordered by `data_emissione`, `numero`)
  - `list_incassate_in_periodo(da: date, a: date) -> list[Invoice]` (issued filter, `stato_pagamento == "incassato"`, `data_incasso` in the window, ordered by `data_incasso`)
  - `list_in_scadenza(da: date, a: date) -> list[Invoice]` (receivable filter, `data_scadenza` between `da` and `a`, ordered by `data_scadenza`)
  - `sum_emesse_in_periodo(da: date, a: date) -> Decimal` (`Σ totale` on the issued filter by `data_emissione`)
  - `sum_incassate_in_periodo(da: date, a: date) -> Decimal` (`Σ totale` on issued and incassato by `data_incasso`)

- [ ] **Step 1: Write the failing tests**

Read the top of `tests/test_invoice_aggregates.py` for the helpers it already has to create issued, paid and overdue invoices (they exist for `sum_da_incassare` / `sum_scaduto`); reuse them. Add:

```python
def test_the_week_reads_split_issued_collected_and_due(db_session: Session, ...) -> None:
    # one invoice issued on 2026-09-08 for 1000, collected on 2026-09-10
    # one invoice issued on 2026-09-01 for 500, due on 2026-09-12, unpaid
    # one invoice issued on 2026-09-15 for 300, unpaid, due 2026-10-15
    repo = InvoiceRepository(db_session)
    week = (date(2026, 9, 7), date(2026, 9, 13))
    assert [i.totale for i in repo.list_emesse_in_periodo(*week)] == [Decimal("1000.00")]
    assert [i.totale for i in repo.list_incassate_in_periodo(*week)] == [Decimal("1000.00")]
    assert [i.totale for i in repo.list_in_scadenza(date(2026, 9, 7), date(2026, 9, 14))] == [Decimal("500.00")]
    assert repo.sum_emesse_in_periodo(*week) == Decimal("1000.00")
    assert repo.sum_incassate_in_periodo(*week) == Decimal("1000.00")
    assert repo.sum_emesse_in_periodo(date(2026, 9, 1), date(2026, 9, 30)) == Decimal("1800.00")
```

Use the file's existing factory helpers for the three invoices (issued via the service so `stato`, `numero` and `data_emissione` are real). Proformas and annulled invoices must not be counted: the issued filter excludes them by construction; add one annulled invoice in the window and assert it is absent.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest -q projects/pigrocrm/packages/core/tests/test_invoice_aggregates.py -k week_reads`
Expected: FAIL with `AttributeError: 'InvoiceRepository' object has no attribute 'list_emesse_in_periodo'`

- [ ] **Step 3: Implement the five methods**

Same shape as `count_emesse_in_periodo` and `sum_da_incassare` (predicates `_issued_filter()`, `_receivable_filter()`; `func.coalesce(func.sum(Invoice.totale), 0)`; `Decimal` result). Example:

```python
    def list_emesse_in_periodo(self, da: date, a: date) -> list[Invoice]:
        """Issued invoices whose own date falls in the window, oldest first: the rows the
        weekly report lists under «Emesse questa settimana» (spec 2026-09-16 §3.1)."""
        stmt = (
            select(Invoice)
            .where(*_issued_filter(), Invoice.data_emissione >= da, Invoice.data_emissione <= a)
            .order_by(Invoice.data_emissione, Invoice.numero)
        )
        return list(self.session.scalars(stmt).all())
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q projects/pigrocrm/packages/core/tests/test_invoice_aggregates.py`
Expected: PASS

- [ ] **Step 5: Lint, types, commit**

```bash
uv run ruff format projects/pigrocrm && uv run ruff check projects/pigrocrm && uv run mypy
git add projects/pigrocrm/packages/core/src/pigrocrm/core/invoices/repository.py projects/pigrocrm/packages/core/tests/test_invoice_aggregates.py
git commit -m "feat(core): the invoice register answers a week: issued, collected, due, and their sums

Five reads on InvoiceRepository over the predicates the dashboards already use, so
the weekly report (spec 2026-09-16 §3.1) lists the same invoices the economic
dashboard counts.

REB-221."
```

---

### Task 3: `WeeklyDigest` and `DigestService.build`

**Files:**
- Create: `projects/pigrocrm/packages/core/src/pigrocrm/core/digest/schemas.py`, `projects/pigrocrm/packages/core/src/pigrocrm/core/digest/service.py`
- Test: `projects/pigrocrm/packages/core/tests/test_digest_build.py`

**Interfaces:**
- Produces `pigrocrm.core.digest.schemas`:

```python
class DigestInvoice(BaseModel):
    invoice_id: UUID
    numero: str            # invoices.naming.numero_completo
    cliente: str
    importo: Decimal
    data: date             # emission, collection or due date depending on the list
    stato: str             # invoice.stato
    stato_pagamento: str
    giorni_di_ritardo: int | None = None

class DigestDealMove(BaseModel):
    deal_id: UUID
    titolo: str
    stage_nome: str
    quando: date

class DigestOffer(BaseModel):
    document_id: UUID
    titolo: str
    giorni: int

class DigestStage(BaseModel):
    stage_nome: str
    numero: int
    valore_totale: Decimal

class DigestSignal(BaseModel):
    codice: str
    etichetta: str
    conteggio: int
    collegamento: str

class WeeklyDigest(BaseModel):
    settimana: str                 # "2026-W38"
    da: date
    a: date
    scadute: list[DigestInvoice]   # overdue, worst first
    in_scadenza: list[DigestInvoice]  # due in the 7 days after `a`
    vinti_da_fatturare: int
    ore_non_fatturate: Decimal
    valore_maturato: Decimal
    emesse: list[DigestInvoice]
    totale_mese_corrente: Decimal
    totale_mese_precedente: Decimal
    incassate: list[DigestInvoice]
    ore: WeekHours | None          # None when the week has no hours
    pipeline: list[DigestStage]
    deal_mossi: list[DigestDealMove]
    offerte_in_attesa: list[DigestOffer]
    segnali: list[DigestSignal]    # only those with conteggio > 0

    @property
    def settimana_ferma(self) -> bool: ...  # no emesse, incassate, ore, deal_mossi
    @property
    def vuoto(self) -> bool: ...            # every list empty and every number zero
```

- Produces `pigrocrm.core.digest.service`:

```python
class DigestService:
    def __init__(self, session: Session, settings: Settings) -> None: ...
    def build(self, actor: Actor, settimana: tuple[date, date]) -> WeeklyDigest: ...

def iso_week(day: date) -> str: ...            # "2026-W38"
def previous_week(settings: Settings) -> tuple[date, date]: ...  # current_week(settings) shifted back 7 days
def week_containing(day: date) -> tuple[date, date]: ...
```

- Consumes: `DashboardService(session).get_operational_dashboard(actor)` (call first), `SollecitiService(session, settings=settings).candidates(actor)`, `InvoiceRepository` (Task 2 methods, `customer_names`), `AnalyticsService(session).unbilled_backlog(actor)`, `TimeEntryRepository(session).week_hours(da, a)`, `TimeEntryRepository.count_won_deals_to_invoice()`, `DealRepository(session).pipeline_summary()`, `ActivityRepository(session).by_kind(["stage_changed"], limit=200)` filtered to `occurred_at` in the week (the payload names the stage: read `deals/service.py` for the keys), `DocumentRepository(session).pending_offers()`, `month_bounds` from `clock.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_digest_build.py
"""What one week of a space becomes, list by list, before any HTML exists."""

def test_an_empty_space_builds_an_empty_digest(db_session, seeded_user_id) -> None:
    digest = DigestService(db_session, settings).build(actor, (date(2026, 9, 7), date(2026, 9, 13)))
    assert digest.vuoto is True
    assert digest.settimana == "2026-W37"

def test_the_week_lists_issued_collected_overdue_and_due(db_session, ...) -> None:
    # arrange: the three invoices of Task 2, a deal moved to another stage on 2026-09-09,
    # a sent offer, 6 hours logged on 2026-09-08
    digest = service.build(actor, (date(2026, 9, 7), date(2026, 9, 13)))
    assert [i.importo for i in digest.emesse] == [Decimal("1000.00")]
    assert [i.importo for i in digest.incassate] == [Decimal("1000.00")]
    assert [i.giorni_di_ritardo for i in digest.scadute] == [...]
    assert digest.ore is not None and digest.ore.ore_totali == Decimal("6.00")
    assert [m.stage_nome for m in digest.deal_mossi] == ["..."]
    assert len(digest.offerte_in_attesa) == 1
    assert digest.settimana_ferma is False

def test_a_quiet_week_is_flagged(...) -> None: ...

def test_previous_week_and_iso_week() -> None:
    settings = Settings(_env_file=None, timezone="Europe/Rome")  # type: ignore[call-arg]
    assert week_containing(date(2026, 9, 16)) == (date(2026, 9, 14), date(2026, 9, 20))
    assert iso_week(date(2026, 9, 14)) == "2026-W38"
```

`db_session` is wrapped in a savepoint transaction, and `get_operational_dashboard` refuses an open transaction: read `tests/test_dashboard_operational.py` for how those tests obtain a usable session (they either commit on the engine or use a fixture of their own) and copy that fixture.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest -q projects/pigrocrm/packages/core/tests/test_digest_build.py`
Expected: FAIL with `ImportError` on `pigrocrm.core.digest.service`

- [ ] **Step 3: Implement schemas and service**

`build` order: (1) `get_operational_dashboard(actor)` → `segnali` (keep `conteggio > 0`), `arretrato` → `ore_non_fatturate`, `valore_maturato`; (2) `SollecitiService.candidates(actor)` → `scadute` (map `SollecitoCandidate` → `DigestInvoice` with `giorni_di_ritardo`, `data=data_scadenza`); (3) `InvoiceRepository` lists and sums for `emesse`, `incassate`, `in_scadenza` (window `a + 1 day .. a + 7 days`), month totals with `month_bounds` for the month containing `a` and the one before; `customer_names` once for every id; `numero_completo(anno, numero)` from `invoices/naming.py`; (4) `week_hours(da, a)` → `ore` if `ore_totali > 0` else `None`; (5) `count_won_deals_to_invoice()`; (6) `pipeline_summary()` → `DigestStage` for stages with `numero > 0`; (7) `by_kind(["stage_changed"], limit=200)` filtered to `da <= occurred_at.date() <= a`, joined to `Deal` titles through `DealRepository`; (8) `pending_offers()`. Every value copied, none computed twice.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q projects/pigrocrm/packages/core/tests/test_digest_build.py projects/pigrocrm/packages/core/tests/test_dashboard_no_arithmetic.py projects/pigrocrm/packages/core/tests/test_clock.py`
Expected: PASS

- [ ] **Step 5: Lint, types, commit**

```bash
git add projects/pigrocrm/packages/core/src/pigrocrm/core/digest projects/pigrocrm/packages/core/tests/test_digest_build.py
git commit -m "feat(core): a space's week as one object: to collect, to issue, issued, collected, hours, pipeline, signals

DigestService.build composes the dashboards, the register and the reminder candidates
into WeeklyDigest (spec 2026-09-16 §3.2); nothing is summed twice and nothing is
rendered yet.

REB-221."
```

---

### Task 4: The mail

**Files:**
- Modify: `projects/pigrocrm/packages/core/src/pigrocrm/core/mail.py` (append `digest_mail`, `digest_subject`, formatting helpers)
- Test: `projects/pigrocrm/packages/core/tests/test_mail.py` (append)

**Interfaces:**
- Produces: `digest_subject(digest: WeeklyDigest) -> str`; `digest_mail(to: str, digest: WeeklyDigest, *, public_url: str) -> Mail`; `euro(value: Decimal) -> str` (`1.800,00 €`); `giorno_breve(day: date) -> str` (`lun 8 set`, Italian abbreviations hard-coded, no locale).
- Links (all with `?da=digest`, or `&da=digest` when a query exists): overdue `{public_url}/app/fatture?scadute=true`, one invoice `{public_url}/app/fatture/{id}`, to issue `{public_url}/app/deal/lista?da_fatturare=true` and `{public_url}/app/ore?fatturato=false`, pipeline `{public_url}/app/deal`, offers `{public_url}/app/documenti/{id}`, signals use `Signal.collegamento`, opt-out `{public_url}/app/impostazioni/profilo`. If a route named here does not exist in `apps/web/src/routes`, use the closest existing one and say so in the commit.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_subject_names_the_facts_that_are_not_zero() -> None:
    assert digest_subject(digest_with(emesse=2, scaduto=Decimal("1800"))) == "La tua settimana: 2 fatture emesse, 1.800,00 € da incassare"
    assert digest_subject(digest_with()) == "La tua settimana in PigroCRM"

def test_only_sections_with_rows_appear_and_every_link_says_da_digest() -> None:
    mail = digest_mail("ada@example.it", digest_with(emesse=1), public_url="https://pigro.letsrebase.com/ada")
    assert "Emesse questa settimana" in mail.html and "Da incassare" not in mail.html
    assert "da=digest" in mail.html and "Non inviarmi più il resoconto" in mail.html
    assert "Emesse questa settimana" in mail.text

def test_external_values_are_escaped() -> None:
    mail = digest_mail("ada@example.it", digest_with(cliente="<b>ACME</b>"), public_url="https://x")
    assert "<b>ACME</b>" not in mail.html and "&lt;b&gt;ACME&lt;/b&gt;" in mail.html

def test_a_quiet_week_offers_the_assistant() -> None:
    assert "Settimana ferma" in digest_mail("a@b.it", digest_with(), public_url="https://x").text
```

Write `digest_with(**overrides)` in the test file as a small factory over `WeeklyDigest`.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest -q projects/pigrocrm/packages/core/tests/test_mail.py -k digest`
Expected: FAIL with `ImportError: cannot import name 'digest_mail'`

- [ ] **Step 3: Implement**

Same shape as `welcome_mail`: `e = html_escape.escape`; a `text` built line by line and an `html` body made of one `<h2>`-style paragraph per section (use the `INK`, `INK_QUIET`, `FONT` constants and `_quiet_link`, `_button` for the one call to action «Apri PigroCRM»), then `Mail(to=to, subject=subject, text=text, html=_frame(subject, body))`. Subject parts in this order, joined by «, »: `N fatture emesse` (`1 fattura emessa`), `X € da incassare` (sum of `scadute`), `N ore registrate`, `N offerte in attesa`, `N deal mossi`; none → «La tua settimana in PigroCRM».

- [ ] **Step 4: Run, lint, commit**

Run: `uv run pytest -q projects/pigrocrm/packages/core/tests/test_mail.py` → PASS

```bash
git add projects/pigrocrm/packages/core/src/pigrocrm/core/mail.py projects/pigrocrm/packages/core/tests/test_mail.py
git commit -m "feat(core): the weekly report as a mail, sections only where there are rows

digest_mail renders WeeklyDigest in the house frame (spec 2026-09-16 §3.5): a subject
made of the week's non-zero facts, one block per section, every link marked da=digest,
the opt-out at the bottom.

REB-221."
```

---

### Task 5: The server-side PostHog event (core telemetry)

**Files:**
- Modify: `projects/pigrocrm/packages/core/pyproject.toml` (`"posthog==7.53.0"` in dependencies, with a comment), then `uv lock` and `uv sync --frozen` at the repository root
- Create: `projects/pigrocrm/packages/core/src/pigrocrm/core/telemetry.py`
- Test: `projects/pigrocrm/packages/core/tests/test_telemetry.py`; `tests/test_architecture.py` must still pass.

**Interfaces:**
- Produces: `class Tracker` with `__init__(self, capture: Callable[..., Any])` and `digest_sent(self, user_id: UUID, *, settimana: str, sezioni: int) -> bool` capturing event `"digest_inviato"` with `distinct_id=str(user_id)`, `properties={"settimana": settimana, "sezioni": sezioni, "via": "server"}`, never raising (returns `False` on exception); `build_client(settings: Settings) -> Posthog | None` (one client per process, `None` without `settings.posthog_key`); `shutdown() -> None`; `tracker_from_settings(settings) -> Tracker | None`. Model: `projects/hub/packages/core/src/rebase_core/analytics.py` in this repository (copy its shape, docstring included, adapted). No `$process_person_profile` flag: CRM users are identified by the browser under the same id.
- Update the comment on `Settings.posthog_key` in `config.py` («Read by `pigrocrm_mcp.analytics`, never by core») to name `core/telemetry.py` too.

- [ ] **Step 1: Write the failing tests** (mirror `projects/hub/packages/core/tests/test_analytics.py`: exact payload, invented nothing, a raising capture answers `False`, no key → `None`, a key builds one client on the EU host, `shutdown()` in a fixture).
- [ ] **Step 2: Run** `uv run pytest -q projects/pigrocrm/packages/core/tests/test_telemetry.py` → FAIL (import).
- [ ] **Step 3: Add the dependency, lock, write the module.**
- [ ] **Step 4: Run** the test file plus `tests/test_architecture.py` → PASS.
- [ ] **Step 5: Commit** (`pyproject.toml`, `uv.lock` at the repository root, `telemetry.py`, `config.py`, the test): `feat(core): a server-side PostHog event, off without a key` … `REB-221.`

---

### Task 6: `DigestRun`: recipients, one send per week, the record

**Files:**
- Create: `projects/pigrocrm/packages/core/src/pigrocrm/core/digest/run.py`
- Test: `projects/pigrocrm/packages/core/tests/test_digest_run.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class DigestOutcome:
    slug: str
    esito: Literal["inviato", "vuoto", "gia_inviato", "nessun_destinatario", "saltato"]
    settimana: str
    destinatari: int = 0
    motivo: str = ""          # for "saltato": the exception's type name, never its text

class DigestRun:
    def __init__(self, session: Session, settings: Settings, *, sender: EmailSender | None,
                 tracker: Tracker | None, public_url: str) -> None: ...
    def send_for_space(self, slug: str, owner_email: str, settimana: tuple[date, date],
                       *, forza: bool = False, dry_run: bool = False) -> DigestOutcome: ...
```

- Behaviour: resolve the actor from `UserRepository(session).get_by_email(owner_email)` as `_cron_actor` does (`Actor(id=user.id, type="system", role=user.ruolo)`); an inactive or missing owner → `saltato`. `vuoto` when the space has no customer, deal, invoice or time entry (one `select(...).limit(1)` each) → nothing written. `gia_inviato` when a `Digest` row for `iso_week(settimana[0])` exists and not `forza`. Recipients: `UserRepository.list_all()` filtered `attivo and digest_settimanale`; none → `nessun_destinatario`, nothing written. Otherwise `DigestService.build`, one `digest_mail` per recipient sent through `sender.send` (a `sender` of `None` or `dry_run` sends nothing and the outcome still says `inviato` with the count, so `--dry-run` shows what would go), then upsert the `Digest` row, `ActivityService.record("digest", digest_row.id, "digest.inviato", actor, {"settimana": ..., "destinatari": n, "sezioni": k})`, `session.commit()`, then `tracker.digest_sent(user.id, settimana=..., sezioni=k)` per recipient (after the commit, never inside).
- Consumes: Task 3 (`DigestService`, `previous_week`, `iso_week`), Task 4 (`digest_mail`), Task 5 (`Tracker`), Task 1 (`Digest`, `digest_settimanale`).

- [ ] **Step 1: Write the failing tests** with `RecordingSender` and a recording capture: a space with data sends to two active opted-in users and not to the opted-out one; the second run answers `gia_inviato` and sends nothing; `forza` sends again and updates the row; an empty space answers `vuoto` and writes no row; `dry_run` writes nothing and sends nothing; the activity payload has counts only; the tracker is called once per recipient.
- [ ] **Step 2: Run** → FAIL (import).
- [ ] **Step 3: Implement** `run.py`.
- [ ] **Step 4: Run** `tests/test_digest_run.py` → PASS.
- [ ] **Step 5: Commit**: `feat(core): the weekly report is sent once per space and week, to whoever asked for it` … `REB-221.`

---

### Task 7: `pigrocrm digest` and its cron line

**Files:**
- Modify: `projects/pigrocrm/packages/core/src/pigrocrm/core/cli.py` (new `digest(...)` function, parser, dispatch)
- Modify: `projects/pigrocrm/docs/superpowers/notes/2026-09-09-gmail-cron-runbook.md` (the second cron line; retitle as the runbook of the cron jobs)
- Test: `projects/pigrocrm/packages/core/tests/test_cli_digest.py`

**Interfaces:**
- Produces: `def digest(*, slug: str | None, data: date | None, forza: bool, dry_run: bool) -> int` in `cli.py`; parser `digest` with `--slug`, `--data YYYY-MM-DD`, `--forza`, `--dry-run`. Iterates the registry exactly as `ensure_space_defaults` (copy its registry block and its per-space `try/finally engine.dispose()`), builds `sender_from_settings(settings)` once and `tracker_from_settings(settings)` once, `public_url = space_base_settings(settings, slug).public_url`, calls `DigestRun(...).send_for_space(...)`, prints one line per space: `{slug}: inviato a {n}` / `{slug}: vuoto` / `{slug}: già inviato per {settimana}` / `{slug}: nessun destinatario` / `{slug}: saltato ({motivo})` (stderr for the last), always returns 0. `--data` uses `week_containing(data)`, otherwise `previous_week(settings)`.
- Runbook line:

```
0 8 * * 1 cd /opt/pigrocrm/projects/pigrocrm && docker compose --env-file ../../.env exec -T api uv run --no-sync pigrocrm digest >> /var/log/pigrocrm-digest.log 2>&1
```

with the note that `0 8` is right only if the host's zone is Europe/Rome (`timedatectl`), else `0 6` in UTC during CEST.

- [ ] **Step 1: Write the failing tests** on the model of `tests/test_tenants.py` (a real registry and one provisioned space in the container) and `tests/test_cli_gmail.py` (monkeypatch `cli.get_settings`, `cli.sender_from_settings` → a `RecordingSender`, `cli.tracker_from_settings` → `None`, `sys.argv`, `capsys`): a provisioned space with one invoice and one admin gets one mail and the line `slug: inviato a 1`; a second `cli.main()` prints `già inviato`; `--dry-run` sends nothing; `--slug altro` touches only that space; an unreachable registry prints the stderr line and exits 0.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the command and the runbook paragraph.
- [ ] **Step 4: Run** `tests/test_cli_digest.py tests/test_cli.py tests/test_cli_gmail.py` → PASS.
- [ ] **Step 5: Commit**: `feat(core): pigrocrm digest walks the registry and mails each space its week` … `REB-221.`

---

### Task 8: The switch in the profile (API field and web)

**Files:**
- Modify (API): nothing beyond Task 1 if `UserService.update` is generic; otherwise `projects/pigrocrm/packages/core/src/pigrocrm/core/auth/service.py`.
- Modify (web): the panel where a person edits their own profile. Find it: `grep -rn "PATCH.*users\|useUpdateUser\|nome" projects/pigrocrm/apps/web/src/features/settings/*.tsx projects/pigrocrm/apps/web/src/features/users 2>/dev/null`; if no self-profile panel exists, add the switch to the users list row of the current user in the users settings panel, guarded by `user.id === auth.user.id`.
- Modify: `projects/pigrocrm/apps/web/src/lib/api-types.ts`: regenerate with the API running (`docker run -d --name reb221-pg -e POSTGRES_PASSWORD=x -p 55498:5432 postgres:17-alpine`, `PIGROCRM_DATABASE_URL=postgresql+psycopg://postgres:x@localhost:55498/postgres uv run alembic -c projects/pigrocrm/packages/core/alembic.ini upgrade head`, `... uv run uvicorn pigrocrm_api.main:app --port 8000`, `pnpm --filter web generate:api`, then stop and remove the container) or, if that fails, edit the two `UserRead`/`UserUpdate` entries by hand to match the schema and say so in the commit.
- Test (web): the panel's existing test file, one case: the switch reads `digest_settimanale` and its change sends `PATCH /api/users/{id}` with `{ digest_settimanale: false }`.

- [ ] Steps: failing web test → run → implement → run `pnpm --filter web test` and `pnpm --filter web lint` and `pnpm --filter web build` → commit `feat(web): a person can switch the weekly report off from their profile` … `REB-221.`

---

### Task 9: The record

**Files:**
- Modify: `docs/design/DECISIONS.md` (one row, 2026-09-16: a scheduled mail exists after slice 6 had left «digest via email» out, and why the cron and not a worker)
- Modify: `projects/pigrocrm/.env.example` (no new variable; add one line under the PostHog key saying the API now sends `digest_inviato` too)
- Modify: `projects/pigrocrm/AGENTS.md` «Running it» or the cron paragraph: the second cron job.

- [ ] Write the three edits, run `uv run ruff check projects/pigrocrm` (no code), commit `docs(pigrocrm): the weekly report in the decisions log, the env example and the runbook` … `REB-221.`

---

## Self-review

- Spec coverage: §3.1 content → Tasks 3 and 4; §3.2 composition → Task 3 (+ Task 2 reads); §3.3 recipients, idempotency, activity, PostHog → Tasks 1, 5, 6; §3.4 command and cron → Task 7; §3.5 mail → Task 4; §3.6 profile → Tasks 1 and 8; §3.7 verification → each task's tests, the live send is the operator's step after the tag.
- Names used across tasks: `WeeklyDigest`, `DigestService.build`, `iso_week`, `previous_week`, `week_containing` (Task 3) are what Tasks 4, 6, 7 import; `digest_mail`, `digest_subject` (Task 4) in Task 6; `Tracker.digest_sent`, `tracker_from_settings`, `shutdown` (Task 5) in Tasks 6, 7; `DigestRun.send_for_space`, `DigestOutcome` (Task 6) in Task 7; `Digest`, `User.digest_settimanale` (Task 1) in Task 6.
