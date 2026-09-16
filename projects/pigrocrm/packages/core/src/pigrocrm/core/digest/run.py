"""Whether a space gets its week, who receives it, and what is left behind.

Spec 2026-09-16 §3.3. Everything that *decides* about the weekly report lives here, and
nothing that composes it does: `DigestService` builds the object, `mail.digest_mail`
renders it, `telemetry.Tracker` reports it, and this module is the one place that answers
"send it? to whom? again?" -- so the cron (§3.4), a resend and a rehearsal are three calls
to one decision rather than three copies of it.

**The order of `send_for_space` is load-bearing.** `DigestService.build` opens the
operational dashboard's read-only `REPEATABLE READ` snapshot, and `DashboardService`
*refuses* a session that already has a transaction in progress. Every read this method
makes first -- the owner, the four emptiness probes, the week's row, the recipients --
autobegins one. So the reads happen, then `session.rollback()` closes that transaction,
and only then does the build run with the snapshot as its first statement. Nothing has
been written at that point, so the rollback discards nothing: it is a release of a read
transaction, not an undo. What the reads produced is kept as plain values -- an `Actor`,
a list of `(id, indirizzo)` pairs, a row id -- precisely so that the `User` objects going
stale across that rollback costs nothing.

**What is written, and when.** One `digests` row per ISO week (the column is unique, which
is what makes a cron that fires twice send once), one timeline entry whose payload is
three counts, one commit, and only then the PostHog events. The tracker is last and
outside the transaction on purpose: a capture that fails must not be able to roll back a
mail that has already left, and it cannot, because there is no longer a transaction for it
to fail inside of.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from pigrocrm.core.activities.service import ActivityService
from pigrocrm.core.actor import Actor, Role
from pigrocrm.core.auth.repository import UserRepository
from pigrocrm.core.config import Settings
from pigrocrm.core.customers.models import Customer
from pigrocrm.core.deals.models import Deal
from pigrocrm.core.digest.models import Digest
from pigrocrm.core.digest.schemas import WeeklyDigest
from pigrocrm.core.digest.service import DigestService, iso_week
from pigrocrm.core.invoices.models import Invoice
from pigrocrm.core.mail import EmailSender, digest_mail
from pigrocrm.core.telemetry import Tracker
from pigrocrm.core.timetracking.models import TimeEntry

# What the timeline entry is filed under. `digest` is not a `fields.EntityType` and is not
# meant to become one: nobody adds custom fields to a mail that was sent. `activities`
# accepts any string, and `attivita`/`google_account` are the precedent.
ENTITA = "digest"
KIND = "digest.inviato"

Esito = Literal["inviato", "vuoto", "gia_inviato", "nessun_destinatario", "saltato"]

# The two `saltato` motives that are not an exception's name. Short machine words, like
# the `esito` literals themselves, and deliberately not a sentence containing the address:
# `motivo` is printed in a cron's log.
TITOLARE_MANCANTE = "titolare_mancante"
TITOLARE_DISATTIVATO = "titolare_disattivato"


@dataclass(frozen=True)
class DigestOutcome:
    """What happened to one space in one week, in the terms §3.4's command prints.

    `motivo` is filled only for `saltato`, and never with an exception's *message*: a
    provider's error text routinely quotes the address it failed on, and this value is
    written to a log and handed back to a command.
    """

    slug: str
    esito: Esito
    settimana: str
    destinatari: int = 0
    motivo: str = ""


def sezioni_con_righe(digest: WeeklyDigest) -> int:
    """How many of §3.1's seven sections have something in them.

    A *section* count, not a list count: «Da incassare» is two lists and one heading, and
    so is «In pipeline» with three. It is what `digest_inviato` carries as `sezioni`, so
    PostHog can tell the week that was worth reading from the one that said «settimana
    ferma», and the timeline entry carries the same number for the same reason.

    `ore` is the one section tested for presence rather than for content: `None` and a
    week of zeros are different statements, and §3.1 drops the section only for the first.
    """
    return sum(
        [
            bool(digest.scadute or digest.in_scadenza),
            bool(digest.vinti_da_fatturare or digest.ore_non_fatturate),
            bool(digest.emesse),
            bool(digest.incassate),
            digest.ore is not None,
            bool(digest.pipeline or digest.deal_mossi or digest.offerte_in_attesa),
            bool(digest.segnali),
        ]
    )


class DigestRun:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        sender: EmailSender | None,
        tracker: Tracker | None,
        public_url: str,
    ) -> None:
        self.session = session
        self.settings = settings
        # `None` for both is the ordinary state of an installation that has configured
        # neither Resend nor PostHog, not an error: the report is still built, still
        # recorded, and simply has nowhere to go.
        self.sender = sender
        self.tracker = tracker
        self.public_url = public_url

    def send_for_space(
        self,
        slug: str,
        owner_email: str,
        settimana: tuple[date, date],
        *,
        forza: bool = False,
        dry_run: bool = False,
    ) -> DigestOutcome:
        """The whole decision for one space, in the order the module docstring gives.

        The four early answers -- `saltato`, `vuoto`, `gia_inviato`, `nessun_destinatario`
        -- are returned before anything is built and write nothing at all. Only the last
        path opens the snapshot, and everything it does after that point is inside the
        `try` below, because half a sent week is worse than an unsent one.
        """
        iso = iso_week(settimana[0])
        utenti = UserRepository(self.session)

        titolare = utenti.get_by_email(owner_email)
        if titolare is None:
            return DigestOutcome(slug, "saltato", iso, motivo=TITOLARE_MANCANTE)
        if not titolare.attivo:
            return DigestOutcome(slug, "saltato", iso, motivo=TITOLARE_DISATTIVATO)
        # `cast` and not a runtime check, exactly as `cli.py`'s `_cron_actor` does it:
        # `Actor` validates `role` against its own literal on construction, so a column
        # holding something else raises there rather than travelling on unnoticed.
        attore = Actor(id=titolare.id, type="system", role=cast(Role, titolare.ruolo))

        if self._spazio_vuoto():
            return DigestOutcome(slug, "vuoto", iso)

        riga_id = self._riga_della_settimana(iso)
        if riga_id is not None and not forza:
            return DigestOutcome(slug, "gia_inviato", iso)

        # Plain values, taken now: the `User` objects behind them expire on the rollback
        # the build needs, and reloading them would reopen the very transaction that
        # rollback exists to close.
        destinatari = [
            (utente.id, utente.email)
            for utente in utenti.list_all()
            if utente.attivo and utente.digest_settimanale
        ]
        if not destinatari:
            return DigestOutcome(slug, "nessun_destinatario", iso)

        try:
            esito, sezioni = self._invia(
                slug,
                iso,
                attore,
                destinatari,
                riga_id,
                settimana,
                dry_run=dry_run,
            )
        except Exception as exc:  # noqa: BLE001 - one space's failure is not the cron's
            # Whatever went wrong, this week is left exactly as it was found: no row, no
            # timeline entry, and a motive the operator can act on without it carrying an
            # address out of the exception's text.
            self.session.rollback()
            return DigestOutcome(slug, "saltato", iso, motivo=type(exc).__name__)

        # Outside the `try` deliberately, and not only after the commit: by this point the
        # mail has gone and the week is recorded, so nothing PostHog can do may turn this
        # answer into `saltato` or roll back a transaction that no longer exists.
        # `sezioni` is `None` for a rehearsal, which reports nothing to anybody.
        if sezioni is not None and self.tracker is not None:
            for user_id, _ in destinatari:
                self.tracker.digest_sent(user_id, settimana=iso, sezioni=sezioni)
        return esito

    # -- the path that sends ----------------------------------------------------------

    def _invia(
        self,
        slug: str,
        iso: str,
        attore: Actor,
        destinatari: list[tuple[UUID, str]],
        riga_id: UUID | None,
        settimana: tuple[date, date],
        *,
        dry_run: bool,
    ) -> tuple[DigestOutcome, int | None]:
        """The outcome, and the section count PostHog is to be told -- `None` when it is
        not to be told anything, which is a rehearsal and only a rehearsal.

        Everything here runs inside the caller's `try`, and the caller does the tracking
        afterwards, so the capture cannot be the reason a committed week reports `saltato`.
        """
        # Nothing has been written yet: this closes the *read* transaction the checks
        # above autobegan, so that the dashboard's snapshot is the first statement of the
        # next one. `DashboardService._open_snapshot` refuses a session in a transaction.
        self.session.rollback()

        digest = DigestService(self.session, self.settings).build(attore, settimana)
        sezioni = sezioni_con_righe(digest)
        indirizzi = [indirizzo for _, indirizzo in destinatari]

        if dry_run:
            # A rehearsal: the report is built so the operator can be told what would go
            # out and to how many people, and then nothing at all happens. Note the
            # asymmetry with a `sender` of `None` below -- that is a real run on an
            # installation with no Resend key, and a real run has to record its week or
            # the next one would send it again.
            #
            # The rollback writes nothing and undoes nothing -- the build only read. It
            # releases the snapshot, which a `REPEATABLE READ` transaction left open would
            # hold for as long as the caller kept the session.
            self.session.rollback()
            return DigestOutcome(slug, "inviato", iso, destinatari=len(destinatari)), None

        if self.sender is not None:
            for indirizzo in indirizzi:
                self.sender.send(digest_mail(indirizzo, digest, public_url=self.public_url))

        riga = self._registra(iso, indirizzi, riga_id)
        # Last touch on the session before the commit, as `ActivityService.record`'s own
        # contract requires: it flushes into this transaction and never commits.
        ActivityService(self.session).record(
            ENTITA,
            riga.id,
            KIND,
            attore,
            {"settimana": iso, "destinatari": len(destinatari), "sezioni": sezioni},
        )
        self.session.commit()

        # The week is out and recorded. The caller reports it to PostHog from here.
        return DigestOutcome(slug, "inviato", iso, destinatari=len(destinatari)), sezioni

    # -- the reads, and the row -------------------------------------------------------

    def _spazio_vuoto(self) -> bool:
        """§2: silence for a space with nothing in it.

        Four existence probes rather than the built report's own `vuoto`, because this is
        the question asked *before* building: a space that has never had a customer should
        cost one bounded query per table on a Monday morning, not seven sections and a
        snapshot. `LIMIT 1` on the primary key: the answer is whether there is a row, not
        how many.
        """
        return all(
            self.session.execute(select(model.id).limit(1)).first() is None
            for model in (Customer, Deal, Invoice, TimeEntry)
        )

    def _riga_della_settimana(self, iso: str) -> UUID | None:
        return self.session.execute(
            select(Digest.id).where(Digest.settimana == iso)
        ).scalar_one_or_none()

    def _registra(self, iso: str, indirizzi: list[str], riga_id: UUID | None) -> Digest:
        """The week's row: created, or -- under `forza` -- moved.

        `digests.settimana` is unique, so a resend cannot be a second row: it updates the
        addresses and the instant, and the row goes on being the answer to «did this week
        go out, and to whom». `datetime.now(UTC)` is the same expression `occurred_at`'s
        column default uses, and it is an instant rather than a calendar day -- the thing
        `db/clock.py` bans is projecting `now()` onto a *date*, which nothing here does.
        """
        if riga_id is None:
            riga = Digest(settimana=iso, inviato_a=indirizzi, occurred_at=datetime.now(UTC))
            self.session.add(riga)
            self.session.flush()
            return riga
        riga = self.session.get_one(Digest, riga_id)
        riga.inviato_a = indirizzi
        riga.occurred_at = datetime.now(UTC)
        self.session.flush()
        return riga
