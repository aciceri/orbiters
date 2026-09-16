"""`pigrocrm digest`: the Monday cron, against a real registry and real spaces.

Spec 2026-09-16 §3.4. The command is the only piece of the weekly report that knows
there is more than one space: it walks the tenant registry, opens each space's own
database and hands `DigestRun` one session per space. So this file provisions two spaces
for real -- `CREATE DATABASE`, the repository's migrations to head, the first admin --
exactly as `test_tenants.py` does, gives each of them one customer and one invoice issued
in the week that has just closed, and then runs `cli.main(["digest", ...])`.

Nothing is asserted against a mock. The sender is a `RecordingSender` holding the real
`Mail` objects the run handed it, and what a space remembers of its week is read back out
of its `digests` table in a connection of the test's own.

The two spaces are provisioned once for the module (a provisioning is a `CREATE DATABASE`
plus thirty-five migrations, and five tests do not need five of them); what a run *writes*
is undone after every test, so each one starts from a space that has never been mailed.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

import pigrocrm.core.cli as cli
from pigrocrm.core.config import Settings
from pigrocrm.core.customers.models import Customer
from pigrocrm.core.db import session_factory, today_local
from pigrocrm.core.digest.service import iso_week
from pigrocrm.core.invoices.models import Invoice
from pigrocrm.core.mail import Mail, RecordingSender
from pigrocrm.core.tenants import (
    TenantService,
    TenantSignup,
    ensure_tenants_database,
)
from pigrocrm.core.tenants.database import tenant_database_name, tenant_database_url

PUBLIC_URL = "https://crm.example.it"
UNO = "prova-digest-uno"
DUE = "prova-digest-due"
# Provisioned like the others and left as it is born: nobody has entered a customer, a
# deal, an invoice or an hour, which is the one space that hears nothing (§2).
VUOTO = "prova-digest-vuoto"
TITOLARI = {UNO: "uno@studio.it", DUE: "due@studio.it"}
SPAZI = (UNO, DUE, VUOTO)
TITOLARE_VUOTO = "vuoto@studio.it"


# --- the container, the registry, and three spaces in it -----------------------------


@pytest.fixture(scope="module")
def settings(db_engine: Engine) -> Settings:
    """The environment the command reads. `public_url` is the root's: each space's own is
    that plus its slug, and that is the difference the mails are checked for."""
    return Settings(
        database_url=db_engine.url.render_as_string(hide_password=False),
        public_url=PUBLIC_URL,
        timezone="Europe/Rome",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture(scope="module")
def registry(settings: Settings) -> Iterator[Engine]:
    engine = ensure_tenants_database(settings)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def spazi(settings: Settings, registry: Engine) -> Iterator[None]:
    """Three provisioned spaces: two with something to report, one just born."""
    session: Session = session_factory(registry)()
    service = TenantService(session, settings)
    try:
        for slug in SPAZI:
            service.provision(
                TenantSignup(
                    slug=slug,
                    nome=f"Studio {slug}",
                    email=TITOLARI.get(slug, TITOLARE_VUOTO),
                )
            )
            if slug in TITOLARI:
                _una_fattura(settings, slug, _settimana_scorsa(settings))
        yield
    finally:
        for slug in SPAZI:
            _drop(settings, slug)
        session.execute(
            text("delete from tenants where slug = any(:slugs)"), {"slugs": list(SPAZI)}
        )
        session.commit()
        session.close()


@pytest.fixture(autouse=True)
def _nessuna_settimana_inviata(settings: Settings, spazi: None) -> Iterator[None]:
    """What a run writes, undone. The `digests` row is what makes the second Monday say
    «già inviato», so a test that left one behind would decide the next one's answer."""
    yield
    for slug in SPAZI:
        engine = _motore(settings, slug)
        try:
            with engine.begin() as connection:
                connection.execute(text("delete from activities where entity_type = 'digest'"))
                connection.execute(text("delete from digests"))
        finally:
            engine.dispose()


@pytest.fixture
def cron(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> RecordingSender:
    """The command as the container runs it, except for the two things that leave the
    machine: Resend becomes a sender that keeps the mails, PostHog is absent -- which is
    the ordinary state of an installation with no key, not a special case."""
    sender = RecordingSender()
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "sender_from_settings", lambda _settings: sender)
    monkeypatch.setattr(cli, "tracker_from_settings", lambda _settings: None)
    return sender


# --- the corpus, and reading a space back --------------------------------------------


def _settimana_scorsa(settings: Settings) -> tuple[date, date]:
    """The week that has just closed, computed here and not through `previous_week`: a
    fixture that derived its window from a function under test would move with it."""
    oggi = today_local(settings)
    lunedi = oggi - timedelta(days=oggi.isoweekday() - 1 + 7)
    return lunedi, lunedi + timedelta(days=6)


def _motore(settings: Settings, slug: str) -> Engine:
    return create_engine(tenant_database_url(settings, tenant_database_name(slug)), future=True)


def _una_fattura(settings: Settings, slug: str, settimana: tuple[date, date]) -> None:
    """One customer and one invoice issued inside the week: enough that the space is not
    empty (§2) and that the report has a section in it."""
    da, a = settimana
    engine = _motore(settings, slug)
    try:
        with session_factory(engine)() as session:
            customer = Customer(ragione_sociale="Cliente Uno", nazione="IT", custom_fields={})
            session.add(customer)
            session.flush()
            session.add(
                Invoice(
                    customer_id=customer.id,
                    tipo="fattura",
                    stato="emessa",
                    stato_pagamento="da_incassare",
                    anno=2026,
                    numero=1,
                    imponibile=Decimal("1000.00"),
                    imposta=Decimal("0.00"),
                    bollo=Decimal("0.00"),
                    totale=Decimal("1000.00"),
                    data_emissione=da + timedelta(days=1),
                    data_scadenza=a + timedelta(days=120),
                    data_incasso=None,
                    tipo_documento="TD01",
                    divisa="EUR",
                    custom_fields={},
                )
            )
            session.commit()
    finally:
        engine.dispose()


def _settimane(settings: Settings, slug: str) -> list[str]:
    """What the space remembers of the weeks it was mailed."""
    engine = _motore(settings, slug)
    try:
        with engine.connect() as connection:
            return list(
                connection.execute(text("select settimana from digests order by settimana"))
                .scalars()
                .all()
            )
    finally:
        engine.dispose()


def _mie(sender: RecordingSender) -> list[Mail]:
    """Only the mails addressed to this file's two owners: the registry is shared with
    whatever else has provisioned a space on this container."""
    return [mail for mail in sender.sent if mail.to in set(TITOLARI.values())]


# --- the command ---------------------------------------------------------------------


def test_the_cron_mails_every_space_its_week_and_prints_one_line_each(
    settings: Settings, cron: RecordingSender, capsys: pytest.CaptureFixture[str]
) -> None:
    iso = iso_week(_settimana_scorsa(settings)[0])

    assert cli.main(["digest"]) == 0

    out = capsys.readouterr().out
    assert f"{UNO}: inviato a 1" in out
    assert f"{DUE}: inviato a 1" in out
    # The space nobody has started using hears nothing, and says so in the same log: a
    # report where every section is empty is the one mail §2 exists to prevent.
    assert f"{VUOTO}: vuoto" in out
    assert TITOLARE_VUOTO not in {mail.to for mail in cron.sent}
    assert sorted(mail.to for mail in _mie(cron)) == sorted(TITOLARI.values())
    # Each space's links are the root's public URL plus its own slug: `space_base_settings`
    # per space, and not the root's for everybody.
    for slug, indirizzo in TITOLARI.items():
        mail = next(mail for mail in _mie(cron) if mail.to == indirizzo)
        assert f"{PUBLIC_URL}/{slug}/app" in mail.text
        assert _settimane(settings, slug) == [iso]


def test_a_week_already_sent_is_not_sent_a_second_time(
    settings: Settings, cron: RecordingSender, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two crons on the same Monday -- a retry, a rerun by hand -- are one mail. The
    `digests` row is unique on the week, and the second run says which week it is skipping
    so the log answers «did last week go out» without opening the database."""
    iso = iso_week(_settimana_scorsa(settings)[0])
    assert cli.main(["digest", "--slug", UNO]) == 0
    capsys.readouterr()

    assert cli.main(["digest", "--slug", UNO]) == 0

    assert capsys.readouterr().out.strip() == f"{UNO}: già inviato per {iso}"
    assert len(_mie(cron)) == 1


def test_a_rehearsal_says_what_would_go_out_and_sends_nothing(
    settings: Settings, cron: RecordingSender, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--dry-run` is how the cron line is verified by hand on the day it is installed.
    It must be distinguishable in the log from the real thing, or the rehearsal reads as
    the week having gone out."""
    assert cli.main(["digest", "--slug", UNO, "--dry-run"]) == 0

    assert capsys.readouterr().out.strip() == f"{UNO}: inviato a 1 (prova)"
    assert _mie(cron) == []
    assert _settimane(settings, UNO) == []


def test_slug_visits_that_space_and_leaves_the_others_alone(
    settings: Settings, cron: RecordingSender, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["digest", "--slug", DUE]) == 0

    out = capsys.readouterr().out
    assert f"{DUE}: inviato a 1" in out
    assert UNO not in out
    assert [mail.to for mail in _mie(cron)] == [TITOLARI[DUE]]
    assert _settimane(settings, UNO) == []


def test_a_slug_that_is_not_in_the_registry_is_one_line_and_not_a_failure(
    cron: RecordingSender, capsys: pytest.CaptureFixture[str]
) -> None:
    """A typo in a cron line must not look like a week that went out, and must not take
    the exit status of the run with it: the other spaces are mailed by other lines."""
    assert cli.main(["digest", "--slug", "prova-digest-mai-esistito"]) == 0

    captured = capsys.readouterr()
    assert captured.err.strip() == "prova-digest-mai-esistito: non nel registro"
    assert captured.out == ""
    assert _mie(cron) == []


def test_a_space_where_everybody_switched_it_off_is_said_and_not_sent(
    settings: Settings, cron: RecordingSender, capsys: pytest.CaptureFixture[str]
) -> None:
    """Switching the report off is a decision the CRM already carries
    (`users.digest_settimanale`), and the cron reports it rather than obeying it in
    silence: a space that receives nothing for weeks has to be distinguishable in the log
    from a space that is not being visited at all."""
    engine = _motore(settings, UNO)
    try:
        with engine.begin() as connection:
            connection.execute(text("update users set digest_settimanale = false"))
        assert cli.main(["digest", "--slug", UNO]) == 0

        assert capsys.readouterr().out.strip() == f"{UNO}: nessun destinatario"
        assert _mie(cron) == []
        assert _settimane(settings, UNO) == []
    finally:
        with engine.begin() as connection:
            connection.execute(text("update users set digest_settimanale = true"))
        engine.dispose()


def test_forza_with_a_day_of_that_week_sends_it_again(
    settings: Settings, cron: RecordingSender, capsys: pytest.CaptureFixture[str]
) -> None:
    """How a week is resent: `--data` names any day of it and `--forza` says the row that
    is already there is not an answer. The row moves, it is not duplicated."""
    lunedi = _settimana_scorsa(settings)[0]
    iso = iso_week(lunedi)
    assert cli.main(["digest", "--slug", UNO]) == 0
    capsys.readouterr()

    assert cli.main(["digest", "--slug", UNO, "--forza", "--data", lunedi.isoformat()]) == 0

    assert capsys.readouterr().out.strip() == f"{UNO}: inviato a 1"
    assert [mail.to for mail in _mie(cron)] == [TITOLARI[UNO], TITOLARI[UNO]]
    assert _settimane(settings, UNO) == [iso]


def test_an_unreachable_registry_is_one_line_on_stderr_and_still_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same contract `ensure-space-defaults` has: this runs from cron, and a registry
    that cannot be reached is a line an operator can act on, never a traceback -- and
    never the URL, which carries the password."""
    sender = RecordingSender()
    rotto = Settings(
        database_url="postgresql+psycopg://utente:segreta@127.0.0.1:1/nessuno",
        _env_file=None,  # type: ignore[call-arg]
    )
    monkeypatch.setattr(cli, "get_settings", lambda: rotto)
    monkeypatch.setattr(cli, "sender_from_settings", lambda _settings: sender)
    monkeypatch.setattr(cli, "tracker_from_settings", lambda _settings: None)

    assert cli.main(["digest"]) == 0

    captured = capsys.readouterr()
    assert "registro degli spazi non raggiungibile" in captured.err
    assert "segreta" not in captured.err
    assert sender.sent == []


# --- the teardown --------------------------------------------------------------------


def _drop(settings: Settings, slug: str) -> None:
    from pigrocrm.core.db.sidecar import drop_database

    drop_database(settings, tenant_database_url(settings, tenant_database_name(slug)))
