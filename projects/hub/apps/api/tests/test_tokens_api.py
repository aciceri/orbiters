"""An admin's tokens over HTTP (REB-213): minted once behind the cookie, listed, revoked."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from rebase_core.admin import AdminService
from rebase_core.config import Settings

CREDENTIALS = {"email": "ivan@orbiters.it", "password": "una-password-lunga"}


def _settings(api_engine: Engine) -> Settings:
    return Settings(
        database_url=api_engine.url.render_as_string(hide_password=False),
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def admin(api_engine: Engine, api_session: Session) -> Iterator[None]:
    AdminService(api_session, _settings(api_engine)).create(
        CREDENTIALS["email"], "Ivan", CREDENTIALS["password"]
    )
    yield
    api_session.rollback()
    for table in ("admin_tokens", "admin_sessions", "admin_users"):
        api_session.execute(text(f"DELETE FROM {table}"))
    api_session.commit()


def _login(client: TestClient) -> None:
    assert client.post("/api/hub/auth/login", json=CREDENTIALS).status_code == 200


def test_tokens_need_the_cookie(client: TestClient, admin: None) -> None:
    assert client.get("/api/hub/tokens").status_code == 401
    assert client.post("/api/hub/tokens", json={"nome": "x"}).status_code == 401


def test_a_token_is_minted_once_listed_and_revoked(
    client: TestClient, admin: None, api_session: Session
) -> None:
    _login(client)
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
    client: TestClient, admin: None, api_session: Session, api_engine: Engine
) -> None:
    AdminService(api_session, _settings(api_engine)).create(
        "ada@orbiters.it", "Ada", "una-password-lunga"
    )
    assert (
        client.post(
            "/api/hub/auth/login",
            json={"email": "ada@orbiters.it", "password": "una-password-lunga"},
        ).status_code
        == 200
    )
    adas = client.post("/api/hub/tokens", json={"nome": "Cursor"}).json()
    client.post("/api/hub/auth/logout")

    _login(client)
    assert client.get("/api/hub/tokens").json() == []
    assert client.delete(f"/api/hub/tokens/{adas['id']}").status_code == 404
