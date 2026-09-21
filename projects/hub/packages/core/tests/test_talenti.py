"""`talenti`: freelancer cards and bare sign-ups as one list, `stato` `lead` for the
bare ones (REB-282)."""

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from rebase_core.freelancers import FreelancerService
from rebase_core.schemas import FreelancerCreate, FreelancerDraft, SignupCreate, StatusChange
from rebase_core.service import SignupService
from rebase_core.talenti import TalentiService

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def clean(hub_session: Session) -> Session:
    yield hub_session  # type: ignore[misc]
    hub_session.rollback()
    hub_session.execute(text("DELETE FROM comments"))
    hub_session.execute(text("DELETE FROM freelancers"))
    hub_session.execute(text("DELETE FROM companies"))
    hub_session.execute(text("DELETE FROM users"))
    hub_session.commit()


def _application(email: str = "ada@studio.it", **extra: object) -> FreelancerCreate:
    payload: dict[str, object] = {
        "nome": "Ada",
        "cognome": "Lovelace",
        "email": email,
        "tariffa_giornaliera": Decimal("450.00"),
        "posizione": "Backend developer",
        "remoto": "remoto",
        "links": ["https://github.com/ada"],
    }
    payload.update(extra)
    return FreelancerCreate(**payload)  # type: ignore[arg-type]


def _signup(session: Session, email: str = "lead@studio.it", **extra: object) -> UUID:
    payload: dict[str, object] = {"email": email, "nome": "Nuovo", "cognome": "Arrivato"}
    payload.update(extra)
    return SignupService(session).subscribe(SignupCreate(**payload)).id  # type: ignore[arg-type]


def _draft(**extra: object) -> FreelancerDraft:
    payload: dict[str, object] = {
        "nome": "Ada",
        "cognome": "Lovelace",
        "linkedin_url": "https://www.linkedin.com/in/ada",
        "posizione": "Backend developer",
        "links": ["https://github.com/ada"],
        "fonti": ["https://www.linkedin.com/in/ada"],
    }
    payload.update(extra)
    return FreelancerDraft(**payload)  # type: ignore[arg-type]


def test_a_bare_signup_is_a_lead_and_a_card_is_its_own_state(clean: Session) -> None:
    FreelancerService(clean).apply(_application("ada@studio.it"), PDF, "cv.pdf", "application/pdf")
    _signup(clean, "lead@studio.it")
    listed = TalentiService(clean).list_recent()
    by_email = {item.email: item for item in listed.items}
    assert by_email["ada@studio.it"].stato == "nuovo"
    assert by_email["ada@studio.it"].origine == "wizard"
    assert by_email["lead@studio.it"].stato == "lead"
    assert by_email["lead@studio.it"].origine == "form"
    assert listed.totale == 2


def test_a_signup_whose_address_already_has_a_card_is_not_also_a_lead(clean: Session) -> None:
    FreelancerService(clean).apply(_application("ada@studio.it"), PDF, "cv.pdf", "application/pdf")
    _signup(clean, "ADA@studio.it")  # same address, different case: has a card already
    listed = TalentiService(clean).list_recent()
    assert [item.email for item in listed.items] == ["ada@studio.it"]
    assert listed.totale == 1
    assert listed.per_stato["lead"] == 0


def test_a_card_drafted_by_an_admin_from_research_is_origine_admin(clean: Session) -> None:
    signup_id = _signup(clean, "ricerca@studio.it")
    FreelancerService(clean).draft_from_signup(signup_id, _draft(), "Claude")
    listed = TalentiService(clean).list_recent()
    item = next(item for item in listed.items if item.email == "ricerca@studio.it")
    assert item.origine == "admin" and item.stato == "nuovo"
    assert item.id != signup_id  # the card has its own row, and its own id


def test_counts_per_state_include_the_leads_and_are_not_bounded_by_the_limit(
    clean: Session,
) -> None:
    service = FreelancerService(clean)
    ids = [
        service.apply(_application(email=f"p{i}@studio.it"), PDF, "cv.pdf", "")[0].id
        for i in range(3)
    ]
    service.set_status(ids[0], StatusChange(stato="contattato"))
    _signup(clean, "lead1@studio.it")
    _signup(clean, "lead2@studio.it")
    listed = TalentiService(clean).list_recent(limit=1)
    assert listed.per_stato == {"nuovo": 2, "contattato": 1, "attivo": 0, "scartato": 0, "lead": 2}
    assert len(listed.items) == 1  # the page is bounded, the counts are not
    assert [item.email for item in listed.items] == ["lead2@studio.it"]  # and the merge kept the newest row across both sources


def test_the_list_is_newest_first_across_both_tables(clean: Session) -> None:
    service = FreelancerService(clean)
    service.apply(_application("old@studio.it"), PDF, "cv.pdf", "")
    _signup(clean, "middle@studio.it")
    service.apply(_application("new@studio.it"), PDF, "cv.pdf", "")
    listed = TalentiService(clean).list_recent()
    assert [item.email for item in listed.items] == [
        "new@studio.it",
        "middle@studio.it",
        "old@studio.it",
    ]


def test_the_stato_filter_selects_leads_or_a_single_freelancer_state(clean: Session) -> None:
    service = FreelancerService(clean)
    service.apply(_application("ada@studio.it"), PDF, "cv.pdf", "")
    _signup(clean, "lead@studio.it")

    only_leads = TalentiService(clean).list_recent(stato="lead")
    assert [item.email for item in only_leads.items] == ["lead@studio.it"]
    assert only_leads.totale == 1

    only_new = TalentiService(clean).list_recent(stato="nuovo")
    assert [item.email for item in only_new.items] == ["ada@studio.it"]
    assert only_new.totale == 1

    # A filter that never lands in the database is simply empty, like
    # `FreelancerService.list_recent`'s own pass-through filter.
    unknown = TalentiService(clean).list_recent(stato="forse")
    assert unknown.items == [] and unknown.totale == 0


def test_an_empty_hub_answers_zero_of_everything(clean: Session) -> None:
    listed = TalentiService(clean).list_recent()
    assert listed.totale == 0
    assert listed.items == []
    assert listed.per_stato == {"nuovo": 0, "contattato": 0, "attivo": 0, "scartato": 0, "lead": 0}
