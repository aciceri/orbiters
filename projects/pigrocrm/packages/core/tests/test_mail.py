"""The CRM's outbound mail: a seam, Resend behind it, and the one mail this slice sends."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from pigrocrm.core.config import Settings
from pigrocrm.core.dashboard.schemas import DayHours, WeekHours
from pigrocrm.core.digest.schemas import (
    DigestDealMove,
    DigestInvoice,
    DigestOffer,
    DigestSignal,
    DigestStage,
    WeeklyDigest,
)
from pigrocrm.core.mail import (
    RESEND_URL,
    Mail,
    RecordingSender,
    ResendSender,
    digest_mail,
    digest_subject,
    euro,
    giorno_breve,
    magic_link_mail,
    sender_from_settings,
    welcome_mail,
)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_without_a_key_there_is_no_sender() -> None:
    assert sender_from_settings(_settings()) is None


def test_with_a_key_the_sender_is_resend_with_the_configured_from() -> None:
    sender = sender_from_settings(
        _settings(resend_api_key="re_x", mail_from="PigroCRM <ciao@x.it>")
    )
    assert isinstance(sender, ResendSender)
    assert sender.sender == "PigroCRM <ciao@x.it>"


def test_resend_posts_one_json_object_with_the_key_as_bearer() -> None:
    calls: list[tuple[str, str, dict[str, str], bytes]] = []

    def http(method: str, url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
        calls.append((method, url, headers, body))
        return 200, b"{}"

    sender = ResendSender("re_x", "PigroCRM <ciao@x.it>", http=http)
    assert sender.send(Mail(to="ada@x.it", subject="s", text="t", html="<p>t</p>")) is True
    (method, url, headers, body) = calls[0]
    assert (method, url) == ("POST", RESEND_URL)
    assert headers["Authorization"] == "Bearer re_x"
    assert b'"to": ["ada@x.it"]' in body and b'"html": "<p>t</p>"' in body


def test_resend_never_raises_and_answers_false_on_a_failure() -> None:
    def boom(method: str, url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
        raise OSError("down")

    mail = Mail(to="a@x.it", subject="s", text="t")
    assert ResendSender("re_x", "x", http=boom).send(mail) is False
    assert ResendSender("re_x", "x", http=lambda *a: (500, b"")).send(mail) is False


def test_the_magic_link_mail_carries_every_link_and_the_minutes() -> None:
    mail = magic_link_mail(
        "ada@x.it",
        [
            ("studio-ada", "https://pigro.test/studio-ada/app/entra?t=abc"),
            ("secondo", "https://pigro.test/secondo/app/entra?t=def"),
        ],
        15,
    )
    assert mail.to == "ada@x.it"
    assert "15 minuti" in mail.text
    assert "https://pigro.test/studio-ada/app/entra?t=abc" in mail.text
    assert "https://pigro.test/secondo/app/entra?t=def" in mail.text
    assert mail.html is not None and "studio-ada" in mail.html and "&lt;" not in mail.text
    # One space: no label, just the door.
    one = magic_link_mail("a@x.it", [("x", "https://pigro.test/x/app/entra?t=abc")], 15)
    assert one.text.count("https://pigro.test/x/app/entra?t=abc") == 1 and "x:" not in one.text
    # A token that tried to close the tag is escaped in the HTML.
    hostile = magic_link_mail("a@x.it", [("x", 'https://pigro.test/x/app/entra?t="><script>')], 15)
    assert hostile.html is not None and "<script>" not in hostile.html


def test_the_recording_sender_keeps_what_it_was_given() -> None:
    recording = RecordingSender()
    mail = Mail(to="a@x.it", subject="s", text="t")
    assert recording.send(mail) is True
    assert recording.sent == [mail]


def test_the_welcome_mail_enters_with_a_link_and_says_what_to_do_first() -> None:
    entra = "https://pigro.test/ada/app/entra?t=abc"
    login = "https://pigro.test/ada/app/login"
    member = welcome_mail("ada@x.it", entra, login, membro=True)
    assert member.subject == "Il tuo spazio PigroCRM è pronto"
    assert member.text.startswith("Ciao,")
    assert entra in member.text and login in member.text
    assert (
        "assistente" in member.text
        and "dati fiscali" in member.text
        and "primo cliente" in member.text
    )
    assert "letsrebase.com/hub/freelance" not in member.text
    assert member.html is not None and entra in member.html
    guest = welcome_mail("bob@x.it", entra, login, membro=False)
    assert "letsrebase.com/hub/freelance" in guest.text
    assert guest.html is not None and "hub/freelance" in guest.html
    hostile = welcome_mail(
        "x@x.it", 'https://pigro.test/x/app/entra?t="><script>', login, membro=True
    )
    assert hostile.html is not None and "<script>" not in hostile.html


# ---- the weekly digest, as a mail ---------------------------------------------------

_WEEK_START = date(2026, 9, 7)  # a Monday


def _invoice(
    *,
    numero: str = "2026/1",
    cliente: str = "Cliente Prova",
    importo: Decimal = Decimal("0"),
    data: date = date(2026, 9, 8),
    stato: str = "emessa",
    stato_pagamento: str = "aperta",
    giorni_di_ritardo: int | None = None,
) -> DigestInvoice:
    return DigestInvoice(
        invoice_id=uuid4(),
        numero=numero,
        cliente=cliente,
        importo=importo,
        data=data,
        stato=stato,
        stato_pagamento=stato_pagamento,
        giorni_di_ritardo=giorni_di_ritardo,
    )


def digest_with(
    *,
    emesse: int = 0,
    scaduto: Decimal = Decimal("0"),
    cliente: str | None = None,
    numero: str | None = None,
    incassate: int = 0,
    vinti_da_fatturare: int = 0,
    ore_non_fatturate: Decimal = Decimal("0"),
    valore_maturato: Decimal = Decimal("0"),
    ore_totali: Decimal | None = None,
    giorni_senza_ore: int = 0,
    pipeline: int = 0,
    deal_mossi: int = 0,
    offerte: int = 0,
    segnali: int = 0,
) -> WeeklyDigest:
    """A `WeeklyDigest` with every list empty and every figure zero -- a still week --
    save for whichever section a test asks for by count. `cliente` or `numero` alone
    (with no `scaduto`) is enough to put one row in «scadute», which is what the
    escaping tests need without also claiming a debt."""
    scadute = (
        [
            _invoice(
                cliente=cliente or "Cliente Prova",
                numero=numero or "2026/1",
                importo=scaduto,
                giorni_di_ritardo=12,
            )
        ]
        if scaduto or cliente is not None or numero is not None
        else []
    )
    ore = (
        WeekHours(
            da=_WEEK_START,
            a=_WEEK_START + timedelta(days=6),
            giorni=[
                DayHours(giorno=_WEEK_START + timedelta(days=i), ore=Decimal("2.00"))
                for i in range(7)
            ],
            giorni_senza_ore=[_WEEK_START + timedelta(days=i) for i in range(giorni_senza_ore)],
            ore_totali=ore_totali,
        )
        if ore_totali is not None
        else None
    )
    return WeeklyDigest(
        settimana="2026-W37",
        da=_WEEK_START,
        a=_WEEK_START + timedelta(days=6),
        scadute=scadute,
        in_scadenza=[],
        vinti_da_fatturare=vinti_da_fatturare,
        ore_non_fatturate=ore_non_fatturate,
        valore_maturato=valore_maturato,
        emesse=[_invoice(cliente=cliente or "Cliente Prova") for _ in range(emesse)],
        totale_mese_corrente=Decimal("0"),
        totale_mese_precedente=Decimal("0"),
        incassate=[_invoice(cliente=cliente or "Cliente Prova") for _ in range(incassate)],
        ore=ore,
        pipeline=[
            DigestStage(stage_nome=f"Fase {i}", numero=1, valore_totale=Decimal("100"))
            for i in range(pipeline)
        ],
        deal_mossi=[
            DigestDealMove(
                deal_id=uuid4(), titolo=f"Deal {i}", stage_nome="Vinto", quando=_WEEK_START
            )
            for i in range(deal_mossi)
        ],
        offerte_in_attesa=[
            DigestOffer(document_id=uuid4(), titolo=f"Offerta {i}", giorni=3)
            for i in range(offerte)
        ],
        segnali=[
            DigestSignal(
                codice=f"S{i}",
                etichetta=f"Segnale {i}",
                conteggio=1,
                collegamento="/app/dashboard",
            )
            for i in range(segnali)
        ],
    )


def test_euro_formats_the_italian_way() -> None:
    assert euro(Decimal("1800")) == "1.800,00 €"
    assert euro(Decimal("0")) == "0,00 €"


def test_giorno_breve_uses_hard_coded_italian_abbreviations() -> None:
    assert giorno_breve(date(2026, 9, 7)) == "lun 7 set"
    assert giorno_breve(date(2026, 1, 1)) == "gio 1 gen"


def test_the_subject_names_the_facts_that_are_not_zero() -> None:
    assert (
        digest_subject(digest_with(emesse=2, scaduto=Decimal("1800")))
        == "La tua settimana: 2 fatture emesse, 1.800,00 € da incassare"
    )
    assert digest_subject(digest_with()) == "La tua settimana in PigroCRM"


def test_the_subject_uses_the_singular_for_one_of_a_kind() -> None:
    assert digest_subject(digest_with(emesse=1)) == "La tua settimana: 1 fattura emessa"


def test_only_sections_with_rows_appear_and_every_link_says_da_digest() -> None:
    mail = digest_mail(
        "ada@example.it", digest_with(emesse=1), public_url="https://pigro.letsrebase.com/ada"
    )
    assert "Emesse questa settimana" in mail.html and "Da incassare" not in mail.html
    assert "da=digest" in mail.html and "Non inviarmi più il resoconto" in mail.html
    # The switch lives in the profile tab every user can reach (spec §3.6), not the
    # admin-only users panel -- the opt-out link must land somewhere a non-admin
    # recipient can actually open.
    assert "https://pigro.letsrebase.com/ada/app/impostazioni/profilo?da=digest" in mail.html
    assert "Emesse questa settimana" in mail.text
    # §3.1 item 3: «Numero, cliente, importo, stato» -- the number is part of the row.
    assert "2026/1" in mail.text and "2026/1" in mail.html


def test_an_issued_row_prints_its_state_word_as_it_is() -> None:
    """§3.1 item 3: «Numero, cliente, importo, stato». The state is the one extra fact
    «Emesse questa settimana» is about, and it is printed as the register spells it --
    there is no mapping table here, so a value added to `StatoPagamento`'s neighbour
    `InvoiceStato` reads in the mail the day it exists rather than the day somebody
    remembers to extend a dictionary in `mail.py`.
    """
    mail = digest_mail("a@b.it", digest_with(emesse=1), public_url="https://x")
    assert "2026/1 — Cliente Prova — 0,00 € — mar 8 set — emessa" in mail.text
    assert mail.html is not None and "mar 8 set — emessa" in mail.html
    # The value itself, not the word «emessa»: another state reads as itself.
    trasmessa = digest_with(emesse=1)
    trasmessa.emesse[0].stato = "trasmessa"
    assert "mar 8 set — trasmessa" in digest_mail("a@b.it", trasmessa, public_url="https://x").text
    # Only the issued rows: «Incassate questa settimana» is a list of what arrived, and
    # the state of an invoice that has been paid says nothing a reader of that heading
    # does not already know.
    incassate = digest_mail("a@b.it", digest_with(incassate=1), public_url="https://x")
    assert "2026/1 — Cliente Prova — 0,00 € — mar 8 set\n" in incassate.text


def test_external_values_are_escaped() -> None:
    mail = digest_mail("ada@example.it", digest_with(cliente="<b>ACME</b>"), public_url="https://x")
    assert mail.html is not None
    assert "<b>ACME</b>" not in mail.html and "&lt;b&gt;ACME&lt;/b&gt;" in mail.html
    hostile = digest_mail(
        "ada@example.it", digest_with(numero="<img src=x onerror=alert(1)>"), public_url="https://x"
    )
    assert hostile.html is not None
    assert "<img src=x" not in hostile.html and "&lt;img src=x" in hostile.html


def test_the_overdue_list_links_to_the_full_list() -> None:
    mail = digest_mail(
        "a@b.it", digest_with(scaduto=Decimal("100")), public_url="https://pigro.test/ada"
    )
    assert mail.html is not None
    assert "https://pigro.test/ada/app/fatture?scadute=true&da=digest" in mail.text


def test_a_quiet_week_offers_the_assistant() -> None:
    mail = digest_mail("a@b.it", digest_with(), public_url="https://x")
    assert "Settimana ferma" in mail.text


def test_the_hours_section_only_appears_with_hours() -> None:
    still = digest_mail("a@b.it", digest_with(), public_url="https://x")
    assert "Le ore" not in still.html
    worked = digest_mail(
        "a@b.it",
        digest_with(ore_totali=Decimal("12.50"), giorni_senza_ore=2),
        public_url="https://x",
    )
    assert "Le ore" in worked.html and "12,50" in worked.text and "5 giorni su 7" in worked.text


def test_every_link_carries_da_digest_including_signals() -> None:
    # `collegamento` is space-relative, the same shape `dashboard/service.py` builds it
    # in; the mail must still resolve it against `public_url`, not hand it out bare.
    mail = digest_mail("a@b.it", digest_with(segnali=1), public_url="https://pigro.test/ada")
    assert mail.html is not None
    assert "https://pigro.test/ada/app/dashboard?da=digest" in mail.html


def test_the_pipeline_section_links_to_the_pipeline() -> None:
    mail = digest_mail("a@b.it", digest_with(pipeline=1), public_url="https://pigro.test/ada")
    assert mail.html is not None and "In pipeline" in mail.html
    assert "https://pigro.test/ada/app/deal?da=digest" in mail.html


def test_da_emettere_only_appears_with_something_to_bill() -> None:
    still = digest_mail("a@b.it", digest_with(), public_url="https://x")
    assert "Da emettere" not in still.html
    mail = digest_mail("a@b.it", digest_with(vinti_da_fatturare=2), public_url="https://x")
    assert "Da emettere" in mail.html and "2 deal vinti da fatturare" in mail.text
    assert "https://x/app/deal/lista?da_fatturare=true&da=digest" in mail.text
