"""PostHog on the MCP surface (ORB-186): off without a key, and with one, every tool
call reaches the client with the actor's identity and the space as a group, while the
tool's own answer to the agent is unchanged."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from mcp import Client
from posthog import Posthog
from posthog.mcp._internal import get_server_tracking_data
from sqlalchemy.orm import Session

from pigrocrm.core.actor import Actor
from pigrocrm.core.config import Settings
from pigrocrm.core.storage import LocalFileStorage
from pigrocrm_mcp import analytics
from pigrocrm_mcp.server import build_server

KEY = "phc_test_only_never_a_real_project"
NOBODY = Actor(id=None, type="mcp", role="admin")


@pytest.fixture(autouse=True)
def no_key_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # A developer's shell may export the key for a live check; these tests decide it.
    monkeypatch.delenv("PIGROCRM_POSTHOG_KEY", raising=False)
    monkeypatch.delenv("PIGROCRM_POSTHOG_HOST", raising=False)


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Posthog, list[dict[str, Any]]]]:
    """A real client whose `capture` is observed instead of sent: the adapter builds
    the payload and calls this, so what is asserted is what PostHog would receive."""
    client = Posthog(KEY, host="https://eu.i.posthog.com", sync_mode=True)
    events: list[dict[str, Any]] = []

    def record(*args: Any, **kwargs: Any) -> None:
        # `Client.capture(event, *, distinct_id=..., properties=...)`: the name travels
        # positionally, the rest by keyword. Normalised so the assertions read one shape.
        events.append({**kwargs, "event": kwargs.get("event", args[0] if args else None)})

    monkeypatch.setattr(client, "capture", record)
    try:
        yield client, events
    finally:
        client.shutdown()


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_without_a_key_build_server_wraps_nothing(mcp_session: Session, tmp_path: Path) -> None:
    settings = _settings()
    assert settings.posthog_key == ""
    mcp = build_server(lambda: mcp_session, lambda: NOBODY, LocalFileStorage(tmp_path), settings)
    # The server `build_server` handed back carries no tracking state: the adapter was
    # never asked. And `build_client` builds nothing to shut down.
    # The adapter keys its state by the low-level server the high-level one wraps.
    assert get_server_tracking_data(mcp._lowlevel_server) is None
    assert analytics.build_client(settings) is None
    analytics.shutdown()


def test_the_space_group_is_the_root_slug_or_root() -> None:
    assert analytics.space_group(_settings()) == "root"
    assert analytics.space_group(_settings(root_slug="studio")) == "studio"


def test_the_identity_is_the_actor_and_the_space() -> None:
    user_id = uuid4()
    identify = analytics.identity_for(
        lambda: Actor(id=user_id, type="user", role="collaboratore"), "studio"
    )
    identity = identify(None, None)
    assert identity is not None
    assert identity.distinct_id == str(user_id)
    assert identity.groups == {"spazio": "studio"}
    assert identity.properties == {"ruolo": "collaboratore", "via": "user"}
    # An actor without an id (the fixtures' admin) stays anonymous rather than sharing
    # one made-up person across every installation.
    assert analytics.identity_for(lambda: NOBODY, "root")(None, None) is None


def test_one_client_per_process_and_shutdown_forgets_it() -> None:
    first = analytics.build_client(_settings(posthog_key=KEY))
    assert first is not None
    assert analytics.build_client(_settings(posthog_key=KEY)) is first
    # Another key or host is another client; the previous one is left to `shutdown`.
    assert (
        analytics.build_client(_settings(posthog_key=KEY, posthog_host="https://x.test"))
        is not first
    )
    analytics.shutdown()
    analytics.shutdown()  # twice is fine: the second finds nothing
    assert analytics.build_client(_settings(posthog_key=KEY)) is not first
    analytics.shutdown()


async def test_with_a_key_a_tool_call_reaches_posthog_with_the_actor(
    mcp_session: Session, tmp_path: Path, captured: tuple[Posthog, list[dict[str, Any]]]
) -> None:
    client, events = captured
    user_id = uuid4()
    actor = Actor(id=user_id, type="user", role="admin")
    # Built without a key so `build_server` installs nothing, then installed by hand with
    # the observed client: what is under test is the wiring, not PostHog's network.
    mcp = build_server(lambda: mcp_session, lambda: actor, LocalFileStorage(tmp_path), _settings())
    # `space` named, as the HTTP transport names it: it wins over the installation's slug.
    settings = _settings(posthog_key=KEY, root_slug="not-this-one")
    assert analytics.install(mcp, settings, lambda: actor, client, space="studio") is True
    assert get_server_tracking_data(mcp._lowlevel_server) is not None

    async with Client(mcp) as agent:
        tools = await agent.list_tools()
        await agent.call_tool("describe_schema", {"entity_type": "customer"})

    names = [event.get("event") for event in events]
    assert "$mcp_tool_call" in names, names
    call = next(event for event in events if event.get("event") == "$mcp_tool_call")
    assert call["distinct_id"] == str(user_id)
    assert call["properties"]["$mcp_tool_name"] == "describe_schema"
    assert call["properties"]["$groups"] == {"spazio": "studio"}
    assert call["properties"]["$mcp_is_error"] is False
    # And the schema an agent learns is untouched: no injected `context` argument.
    describe = next(tool for tool in tools.tools if tool.name == "describe_schema")
    assert "context" not in (describe.input_schema.get("properties") or {})


async def test_a_refused_call_keeps_its_message_and_counts_as_an_error(
    mcp_session: Session, tmp_path: Path, captured: tuple[Posthog, list[dict[str, Any]]]
) -> None:
    """`_guard` turns a DomainError into guidance for the agent. With the wrapper on,
    the agent reads the same sentence, and PostHog sees one call flagged as an error and
    no `$exception`: a not-found is not a defect to track."""
    client, events = captured
    actor = Actor(id=uuid4(), type="user", role="admin")
    missing = str(uuid4())

    async def refused(server: Any) -> str:
        async with Client(server) as agent:
            result = await agent.call_tool("get_customer", {"customer_id": missing})
            assert result.is_error
        return " ".join(getattr(block, "text", "") for block in result.content)

    plain = build_server(
        lambda: mcp_session, lambda: actor, LocalFileStorage(tmp_path), _settings()
    )
    before = await refused(plain)

    wrapped = build_server(
        lambda: mcp_session, lambda: actor, LocalFileStorage(tmp_path), _settings()
    )
    analytics.install(wrapped, _settings(posthog_key=KEY), lambda: actor, client)
    after = await refused(wrapped)

    assert before == after and before
    calls = [e for e in events if e.get("event") == "$mcp_tool_call"]
    assert len(calls) == 1
    assert calls[0]["properties"]["$mcp_is_error"] is True
    assert "$exception" not in [e.get("event") for e in events]
