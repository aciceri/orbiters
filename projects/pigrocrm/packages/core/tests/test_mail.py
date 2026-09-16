"""The CRM's outbound mail: a seam, Resend behind it, and the one mail this slice sends."""

import logging
import urllib.request

import pytest

from pigrocrm.core.config import Settings
from pigrocrm.core.mail import (
    RESEND_URL,
    USER_AGENT,
    Mail,
    RecordingSender,
    ResendSender,
    magic_link_mail,
    sender_from_settings,
    urllib_call,
    welcome_mail,
)


class _Response:
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, amt: int = -1) -> bytes:
        return b"{}"


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


def test_every_call_names_itself_unless_the_caller_already_did(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cloudflare in front of Resend answers `403 error code: 1010` to urllib's default
    signature: without a name of our own every link by mail is refused before reaching
    the API. Found in production on 2026-09-16 (REB-261), with no mail ever delivered
    since the feature shipped; the hub's seam learned the same lesson on 2026-09-10."""
    seen: list[urllib.request.Request] = []

    def fake_open(request: urllib.request.Request, timeout: float) -> _Response:
        seen.append(request)
        return _Response()

    # `mail.urllib_call` resolves `urllib.request.urlopen` at call time, so patching the
    # module attribute is enough and reaches no private name of the module under test.
    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    urllib_call("POST", "https://api.example.test/x", {"Content-Type": "application/json"}, b"{}")
    urllib_call("GET", "https://api.example.test/y", {"User-Agent": "altro/1"}, b"")
    assert seen[0].get_header("User-agent") == USER_AGENT
    assert USER_AGENT.startswith("pigrocrm/")
    assert seen[1].get_header("User-agent") == "altro/1"
    assert seen[0].get_header("Content-type") == "application/json"


def test_a_refused_send_leaves_a_line_behind_with_no_address_and_no_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`send` answering `False` is dropped by the caller's background task, so the log
    is the only trace a mail did not leave. The status is enough to tell a blocked
    signature from a rejected address; neither the recipient nor the key may appear."""
    mail = Mail(to="ada@x.it", subject="s", text="t")
    with caplog.at_level(logging.WARNING):
        assert (
            ResendSender("re_secret", "x", http=lambda *a: (403, b"error code: 1010")).send(mail)
            is False
        )
    assert "403" in caplog.text
    assert "ada@x.it" not in caplog.text
    assert "re_secret" not in caplog.text


def test_a_send_that_never_reached_the_provider_leaves_a_line_too(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The other silent path: no status at all, because the call itself failed."""

    def boom(method: str, url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
        raise OSError("down")

    with caplog.at_level(logging.WARNING):
        assert ResendSender("re_secret", "x", http=boom).send(Mail("a@x.it", "s", "t")) is False
    assert caplog.text != ""
    assert "a@x.it" not in caplog.text
    assert "re_secret" not in caplog.text
