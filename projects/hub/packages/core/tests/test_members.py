"""The member area: the freelancer card, and what its owner may change once in.

The way in -- the magic link, sessions, `resolve` -- moved to `rebase_core.users`
(REB-278) and is tested in `test_users.py`; this file keeps what is specific to the
freelancer card.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from rebase_core.comments import CommentService
from rebase_core.config import Settings
from rebase_core.errors import NotFound, ValidationFailed
from rebase_core.freelancers import FreelancerService
from rebase_core.members import MemberService
from rebase_core.models import Freelancer
from rebase_core.schemas import FreelancerCreate, MemberProfile, MemberUpdate, StatusChange
from rebase_core.users import UserService

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\n%%EOF\n"

GOOD = {
    "nome": "Ada",
    "cognome": "Lovelace",
    "linkedin_url": "https://www.linkedin.com/in/ada",
    "tariffa_giornaliera": "450",
    "posizione": "Backend developer",
    "remoto": "remoto",
    "links": ["https://github.com/ada", " "],
}


def test_member_update_applies_the_wizards_rules_and_nothing_else() -> None:
    update = MemberUpdate(**GOOD)
    assert update.nome == "Ada" and update.tariffa_giornaliera == Decimal("450")
    with pytest.raises(ValidationError):
        MemberUpdate(**{**GOOD, "email": "ada@studio.it"})  # type: ignore[arg-type]


def test_freelancer_create_strips_blank_links() -> None:
    assert FreelancerCreate(**GOOD, email="ada@studio.it").links == ["https://github.com/ada"]


def test_member_profile_carries_no_admin_field() -> None:
    fields = set(MemberProfile.model_fields)
    assert {"nome", "cognome", "email", "cv_filename", "cv_size", "links"} <= fields
    assert not fields & {"stato", "note", "utm_source", "utm_campaign", "cv_bytes"}


@pytest.fixture
def members(hub_engine: Engine, hub_session: Session) -> MemberService:
    yield MemberService(hub_session)
    hub_session.rollback()
    for table in ("sessions", "magic_link_tokens", "comments", "freelancers", "users"):
        hub_session.execute(text(f"DELETE FROM {table}"))
    hub_session.commit()


@pytest.fixture
def settings(hub_engine: Engine) -> Settings:
    return Settings(
        database_url=hub_engine.url.render_as_string(hide_password=False),
        hub_url="http://localhost:5180/hub",
        _env_file=None,  # type: ignore[call-arg]
    )


def _apply(session: Session, email: str = "ada@studio.it") -> UUID:
    read, _ = FreelancerService(session).apply(
        FreelancerCreate(**GOOD, email=email), PDF, "Ada CV.pdf", "application/pdf"
    )
    return read.id


def _draft_card(session: Session, email: str = "ada@studio.it") -> UUID:
    from rebase_core.schemas import FreelancerDraft, SignupCreate
    from rebase_core.service import SignupService

    signup = SignupService(session).subscribe(
        SignupCreate(email=email, nome="Ada", cognome="Lovelace")
    )
    draft = FreelancerDraft(
        nome="Ada",
        cognome="Lovelace",
        posizione="Backend developer",
        fonti=["https://www.linkedin.com/in/ada"],
    )
    return FreelancerService(session).draft_from_signup(signup.id, draft, "Claude").id


def test_an_update_changes_the_row_and_leaves_one_comment_naming_what_moved(
    members: MemberService, hub_session: Session
) -> None:
    freelancer_id = _apply(hub_session)
    FreelancerService(hub_session).set_status(
        freelancer_id, StatusChange(stato="contattato", note="da sentire")
    )

    unchanged = members.update(freelancer_id, MemberUpdate(**GOOD))
    assert unchanged.tariffa_giornaliera == Decimal("450")
    assert CommentService(hub_session).list("freelancer", freelancer_id) == []

    changed = members.update(
        freelancer_id,
        MemberUpdate(**{**GOOD, "tariffa_giornaliera": "500", "links": []}),
    )
    assert changed.tariffa_giornaliera == Decimal("500") and changed.links == []
    thread = CommentService(hub_session).list("freelancer", freelancer_id)
    assert len(thread) == 1
    assert thread[0].testo == "Profilo aggiornato dalla persona: tariffa giornaliera, link"
    assert thread[0].autore == "Ada Lovelace"

    admin_view = FreelancerService(hub_session).get(freelancer_id)
    assert (admin_view.stato, admin_view.note) == ("contattato", "da sentire")


def test_a_name_change_is_also_written_onto_the_linked_user(
    members: MemberService, hub_session: Session
) -> None:
    """`GET /me` reads `nome`/`cognome`/`linkedin_url` off `users`, so a member's own
    edit here has to land there too, in the same commit (REB-278's "no dual write")."""
    freelancer_id = _apply(hub_session)
    row = hub_session.scalar(select(Freelancer).where(Freelancer.id == freelancer_id))
    assert row is not None
    members.update(freelancer_id, MemberUpdate(**{**GOOD, "nome": "Augusta", "cognome": "King"}))
    user = UserService(hub_session).by_email("ada@studio.it")
    assert user is not None
    assert (user.nome, user.cognome) == ("Augusta", "King")


def test_a_new_cv_is_checked_like_the_wizards_and_leaves_its_comment(
    members: MemberService, hub_session: Session
) -> None:
    freelancer_id = _apply(hub_session)
    with pytest.raises(ValidationFailed) as refused:
        members.replace_cv(freelancer_id, b"non un pdf", "cv.pdf", "application/pdf")
    assert refused.value.details["field"] == "cv"

    new_pdf = PDF + b"\n% versione 2\n"
    profile = members.replace_cv(freelancer_id, new_pdf, "Ada 2026.pdf", "application/pdf")
    assert (profile.cv_filename, profile.cv_size) == ("Ada 2026.pdf", len(new_pdf))
    assert members.cv(freelancer_id).content == new_pdf
    thread = CommentService(hub_session).list("freelancer", freelancer_id)
    assert [comment.testo for comment in thread] == ["CV aggiornato dalla persona"]


def test_a_row_that_is_not_there_is_not_found(members: MemberService) -> None:
    missing = UUID("00000000-0000-7000-8000-000000000000")
    with pytest.raises(NotFound):
        members.profile(missing)
    with pytest.raises(NotFound):
        members.update(missing, MemberUpdate(**GOOD))


def test_a_signed_in_person_with_no_card_gets_a_named_404(
    members: MemberService, hub_session: Session
) -> None:
    """An admin promoted with no freelancer card (§1): `card_for_user`/`require_card`
    answer the shape `GET /me`'s mutation routes need to refuse cleanly."""
    user = UserService(hub_session).get_or_create("ivan@rebase.it", "Ivan", "Fiore")
    assert members.card_for_user(user.id) is None
    with pytest.raises(NotFound) as refused:
        members.require_card(user.id)
    assert refused.value.details["entity"] == "scheda"


def test_me_read_answers_the_identity_and_the_card_together(
    members: MemberService, hub_session: Session
) -> None:
    freelancer_id = _apply(hub_session)
    user = UserService(hub_session).by_email("ada@studio.it")
    assert user is not None
    me = members.me_read(user.id)
    assert me.ha_scheda is True and me.nome == "Ada" and me.role == "member"
    assert me.cv_filename == "Ada CV.pdf" and me.completa is True

    bare = UserService(hub_session).get_or_create("ivan@rebase.it", "Ivan", "Fiore")
    bare_read = members.me_read(bare.id)
    assert bare_read.ha_scheda is False
    assert (bare_read.cv_filename, bare_read.tariffa_giornaliera, bare_read.links) == (
        None,
        None,
        [],
    )
    assert bare_read.completa is False
    assert freelancer_id  # the fixture's card is untouched by the bare read


# ---- completing a card an admin wrote from a signup (ORB-155) -------------------------


def test_an_incomplete_card_reads_as_such_and_has_no_cv_to_download(
    members: MemberService, hub_session: Session
) -> None:
    freelancer_id = _draft_card(hub_session)
    profile = members.profile(freelancer_id)
    assert profile.completa is False
    assert (profile.cv_filename, profile.tariffa_giornaliera, profile.remoto) == (None, None, None)
    with pytest.raises(NotFound):
        members.cv(freelancer_id)


def test_a_wizard_card_that_came_without_a_cv_is_completed_from_the_area(
    members: MemberService, hub_session: Session
) -> None:
    """The promise the wizard makes when it lets somebody past the CV: the card is
    theirs already, it is simply not `completa`, and the upload here is what finishes
    it. The same ending as a card an admin drafted, from the other beginning."""
    freelancer_id = (
        FreelancerService(hub_session).apply(FreelancerCreate(**GOOD, email="ada@studio.it"))[0].id
    )
    assert members.profile(freelancer_id).completa is False
    with pytest.raises(NotFound):
        members.cv(freelancer_id)

    after_cv = members.replace_cv(freelancer_id, PDF, "Ada CV.pdf", "application/pdf")
    assert after_cv.completa is True and after_cv.cv_filename == "Ada CV.pdf"
    texts = [c.testo for c in CommentService(hub_session).list("freelancer", freelancer_id)]
    assert texts[0] == "CV caricato dalla persona"


def test_the_person_completes_the_card_and_takes_it_over(
    members: MemberService, hub_session: Session
) -> None:
    freelancer_id = _draft_card(hub_session)
    after_answers = members.update(freelancer_id, MemberUpdate(**GOOD))
    assert after_answers.completa is False  # the CV is still missing
    after_cv = members.replace_cv(freelancer_id, PDF, "Ada CV.pdf", "application/pdf")
    assert after_cv.completa is True and after_cv.cv_filename == "Ada CV.pdf"
    row = hub_session.scalar(select(Freelancer).where(Freelancer.id == freelancer_id))
    assert row is not None and row.compilata_da == "persona"
    texts = [c.testo for c in CommentService(hub_session).list("freelancer", freelancer_id)]
    assert texts[0] == "CV caricato dalla persona"
    assert texts[1].startswith("Profilo aggiornato dalla persona: ")
    assert "tariffa giornaliera" in texts[1] and "modalità di lavoro" in texts[1]


def test_confirming_a_researched_card_unchanged_still_makes_it_the_persons(
    members: MemberService, hub_session: Session
) -> None:
    freelancer_id = _draft_card(hub_session)
    members.update(
        freelancer_id,
        MemberUpdate(**{**GOOD, "linkedin_url": None, "links": []}),
    )
    # Nothing but the rate and the remote option moved the first time; the second call
    # sends the very same answers, and the card still says «persona» afterwards.
    row = hub_session.scalar(select(Freelancer).where(Freelancer.id == freelancer_id))
    assert row is not None
    row.compilata_da = "admin"
    hub_session.commit()
    members.update(freelancer_id, MemberUpdate(**{**GOOD, "linkedin_url": None, "links": []}))
    hub_session.refresh(row)
    assert row.compilata_da == "persona"
    texts = [c.testo for c in CommentService(hub_session).list("freelancer", freelancer_id)]
    assert texts[0] == "Scheda confermata dalla persona"


# ---- who entered, and when (ORB-158) ----------------------------------------------------


def test_entering_is_recorded_and_the_card_and_the_stats_read_it_back(
    members: MemberService, hub_session: Session, settings: Settings
) -> None:
    from rebase_core.logins import LoginService

    ada = _apply(hub_session, "ada@studio.it")
    _apply(hub_session, "bob@studio.it")
    ada_row = hub_session.scalar(select(Freelancer).where(Freelancer.id == ada))
    assert ada_row is not None
    before = LoginService(hub_session).stats()
    assert (before.totale, before.membri, before.membri_totali) == (0, 0, 2)
    assert FreelancerService(hub_session).get(ada).accessi == 0

    users = UserService(hub_session, settings)
    for _ in range(2):
        mail = users.request_link("ada@studio.it")
        assert mail is not None
        raw = mail.text.split("/entra?t=")[1].split()[0]
        assert users.enter(raw) is not None
    # A spent link and a wrong token open nothing, so they record nothing either.
    assert users.enter("non-un-token-vero-ma-lungo-abbastanza") is None

    card = FreelancerService(hub_session).get(ada)
    assert card.accessi == 2 and card.ultimo_accesso is not None
    listed = {item.email: item for item in FreelancerService(hub_session).list_recent().items}
    assert listed["ada@studio.it"].accessi == 2
    assert listed["bob@studio.it"].accessi == 0 and listed["bob@studio.it"].ultimo_accesso is None

    stats = LoginService(hub_session).stats()
    assert (stats.totale, stats.membri, stats.membri_totali, stats.ultimi_7_giorni) == (2, 1, 2, 2)
    assert [login.email for login in stats.recenti] == ["ada@studio.it", "ada@studio.it"]
    assert stats.recenti[0].logged_at >= stats.recenti[1].logged_at
    assert stats.recenti[0].user_id == ada_row.user_id


# ---- the welcome mailing (ORB-157) ------------------------------------------------------


def test_the_welcome_mailing_speaks_to_every_address_the_hub_knows(
    members: MemberService, hub_session: Session, settings: Settings
) -> None:
    from rebase_core.cli import send_welcome
    from rebase_core.mail import RecordingSender
    from rebase_core.schemas import SignupCreate
    from rebase_core.service import SignupService

    _apply(hub_session, "ada@studio.it")  # a card the person filled, no signup
    _draft_card(hub_session, "bruna@studio.it")  # a signup and a card we drafted
    SignupService(hub_session).subscribe(
        SignupCreate(email="carlo@studio.it", nome="Carlo", cognome="Verdi")
    )  # a signup and nothing else
    sender = RecordingSender()
    outcomes = send_welcome(hub_session, settings, sender, None)
    assert outcomes == [
        ("bruna@studio.it", "inviata (admin)"),
        ("carlo@studio.it", "inviata (nessuna)"),
        ("ada@studio.it", "inviata (persona)"),
    ]
    by_to = {mail.to: mail for mail in sender.sent}
    assert "http://localhost:5180/hub/accedi" in by_to["ada@studio.it"].text
    assert "scheda è completa" in by_to["ada@studio.it"].text
    assert "- Posizione: Backend developer" in by_to["bruna@studio.it"].text
    assert "offerta in linea" in by_to["bruna@studio.it"].text
    assert "http://localhost:5180/hub/freelance" in by_to["carlo@studio.it"].text
    assert by_to["carlo@studio.it"].text.startswith("Ciao Carlo,")

    named = send_welcome(
        hub_session, settings, RecordingSender(), ["ADA@studio.it", "nessuno@studio.it"]
    )
    assert named == [
        ("ada@studio.it", "inviata (persona)"),
        ("nessuno@studio.it", "indirizzo sconosciuto"),
    ]
    hub_session.execute(text("DELETE FROM signups"))
    hub_session.commit()
