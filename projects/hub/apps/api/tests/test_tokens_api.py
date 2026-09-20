"""An admin's tokens over HTTP (REB-213): minted once behind the cookie, listed, revoked."""

import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from rebase_api.deps import get_sender
from rebase_core.mail import RecordingSender
from rebase_core.models import User

ADMIN_EMAIL = "ivan@rebase.it"


@pytest.fixture
def sender(client: TestClient) -> Iterator[RecordingSender]:
    recording = RecordingSender()
    client.app.dependency_overrides[get_sender] = lambda: recording  # type: ignore[attr-defined]
    yield recording


def _bootstrap_admin(session: Session, email: str, nome: str) -> None:
    """The users row migration A would have backfilled for a pre-existing admin."""
    session.add(User(email=email, nome=nome, cognome="", role="admin"))
    session.commit()


@pytest.fixture
def admin(api_session: Session) -> Iterator[None]:
    _bootstrap_admin(api_session, ADMIN_EMAIL, "Ivan")
    yield
    api_session.rollback()
    for table in ("admin_tokens", "users"):
        api_session.execute(text(f"DELETE FROM {table}"))
    api_session.commit()


def _login(client: TestClient, sender: RecordingSender, email: str = ADMIN_EMAIL) -> None:
    assert client.post("/api/hub/auth/link", json={"email": email}).status_code == 202
    match = re.search(r"/entra\?t=([A-Za-z0-9_-]+)", sender.sent[-1].text)
    assert match
    assert client.post("/api/hub/auth/enter", json={"token": match.group(1)}).status_code == 200


def test_tokens_need_the_cookie(client: TestClient, admin: None) -> None:
    assert client.get("/api/hub/tokens").status_code == 401
    assert client.post("/api/hub/tokens", json={"nome": "x"}).status_code == 401


def test_a_token_is_minted_once_listed_and_revoked(
    client: TestClient, admin: None, api_session: Session, sender: RecordingSender
) -> None:
    _login(client, sender)
    created = client.post("/api/hub/tokens", json={})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["nome"] == "Claude Code" and body["token"].startswith("reb_")
    assert body["prefix"] == body["token"][:12]

    listed = client.get("/api/hub/tokens").json()
    assert [row["id"] for row in listed] == [body["id"]]
    assert "token" not in listed[0] and "token_hash" not in listed[0]

    assert client.post("/api/hub/tokens", json={"nome": "   "}).status_code == 422
    assert client.post("/api/hub/tokens", json={"nome": "x" * 121}).status_code == 422

    assert client.delete(f"/api/hub/tokens/{body['id']}").status_code == 204
    [row] = client.get("/api/hub/tokens").json()
    assert row["revoked_at"] is not None


def test_another_admins_token_is_not_found(
    client: TestClient, admin: None, api_session: Session, sender: RecordingSender
) -> None:
    _bootstrap_admin(api_session, "ada@rebase.it", "Ada")
    _login(client, sender, "ada@rebase.it")
    adas = client.post("/api/hub/tokens", json={"nome": "Cursor"}).json()
    client.post("/api/hub/me/logout")

    _login(client, sender)
    assert client.get("/api/hub/tokens").json() == []
    assert client.delete(f"/api/hub/tokens/{adas['id']}").status_code == 404
