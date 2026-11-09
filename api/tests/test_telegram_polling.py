"""The polling loop and the HTTP client against a fake Telegram Bot API (httpx2.MockTransport).

No request ever leaves the process: the fake answers getMe, getUpdates and sendMessage from a
script, and records every call so the tests can check offsets, retries and reply payloads.
"""

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from financas import telegram_bot
from financas.config import Settings
from financas.models import Origin, Transaction, User
from financas.services.auth import create_user
from financas.services.telegram_link import issue_pairing_code
from financas.telegram import replies
from financas.telegram.bot import IncomingMessage
from financas.telegram.client import (
    Backoff,
    TelegramClient,
    TelegramError,
    TelegramUnavailableError,
    Update,
)
from financas.telegram.polling import poll
from tests.helpers import NOW

TOKEN = "123456:SEGREDO-DO-BOT"
CHAT = 4242

Script = list[object]  # each item: a list of updates, an httpx2.Response or an exception


def text_update(
    update_id: int, text: str, chat_id: int = CHAT, chat_type: str = "private"
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1_793_000_000,
            "chat": {"id": chat_id, "type": chat_type, "first_name": "Ana"},
            "from": {"id": chat_id, "is_bot": False, "first_name": "Ana"},
            "text": text,
        },
    }


def ok(result: object) -> httpx2.Response:
    return httpx2.Response(200, json={"ok": True, "result": result})


def failure(status: int, description: str, **parameters: object) -> httpx2.Response:
    body: dict[str, object] = {"ok": False, "error_code": status, "description": description}
    if parameters:
        body["parameters"] = parameters
    return httpx2.Response(status, json=body)


class FakeTelegram:
    """Scripted Bot API. When the getUpdates script runs out it sets `stop` and returns []."""

    def __init__(self, updates: Script | None = None, sends: Script | None = None) -> None:
        self.updates = list(updates or [])
        self.sends = list(sends or [])
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.urls: list[str] = []
        self.stop = asyncio.Event()
        self.hang_when_empty = False
        self.waiting = asyncio.Event()

    def sent(self) -> list[dict[str, Any]]:
        return [payload for method, payload in self.calls if method == "sendMessage"]

    def offsets(self) -> list[object]:
        return [payload.get("offset") for method, payload in self.calls if method == "getUpdates"]

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        payload: dict[str, Any] = json.loads(request.content or b"{}")
        self.calls.append((method, payload))
        self.urls.append(str(request.url))
        if method == "getMe":
            return ok({"id": 1, "is_bot": True, "username": "financas_teste_bot"})
        if method == "sendMessage":
            return self._next(self.sends, request) if self.sends else ok({"message_id": 1})
        if payload.get("timeout") == 0 or self.updates:
            return self._next(self.updates, request) if self.updates else ok([])
        if self.hang_when_empty:
            self.waiting.set()
            await asyncio.Event().wait()  # a long poll with nothing new, until cancelled
        self.stop.set()
        return ok([])

    @staticmethod
    def _next(script: Script, request: httpx2.Request) -> httpx2.Response:
        item = script.pop(0)
        if isinstance(item, Exception):
            if isinstance(item, httpx2.RequestError):
                item.request = request
            raise item
        if isinstance(item, httpx2.Response):
            return item
        return ok(item)


def run_poll(
    fake: FakeTelegram,
    handle: Callable[[IncomingMessage], str | None],
    sleeps: list[float] | None = None,
) -> None:
    async def scenario() -> None:
        async def sleep(seconds: float) -> None:
            if sleeps is not None:
                sleeps.append(seconds)

        async with httpx2.AsyncClient(transport=httpx2.MockTransport(fake)) as http:
            client = TelegramClient(TOKEN, http, backoff=Backoff(1, 60), sleep=sleep)
            await poll(client, handle, timeout=30, stop=fake.stop)

    asyncio.run(scenario())


def echo(message: IncomingMessage) -> str:
    return f"eco: {message.text}"


def test_offset_advances_and_each_message_gets_a_plain_text_reply() -> None:
    fake = FakeTelegram(updates=[[text_update(10, "oi"), text_update(11, "tudo bem?")], []])

    run_poll(fake, echo)

    assert fake.offsets() == [None, 12, 12]
    assert fake.sent() == [
        {"chat_id": CHAT, "text": "eco: oi"},
        {"chat_id": CHAT, "text": "eco: tudo bem?"},
    ]
    first_poll = fake.calls[0][1]
    assert (first_poll["timeout"], first_poll["allowed_updates"]) == (30, ["message"])


def test_network_errors_5xx_and_429_are_retried_with_backoff() -> None:
    fake = FakeTelegram(
        updates=[
            httpx2.ConnectError("sem rede"),
            failure(502, "Bad Gateway"),
            failure(429, "Too Many Requests: retry after 7", retry_after=7),
            [text_update(1, "oi")],
        ],
        sends=[httpx2.ReadTimeout("lento"), ok({"message_id": 1})],
    )
    sleeps: list[float] = []

    run_poll(fake, echo, sleeps)

    # getUpdates: 1 s, 2 s, then the 7 s Telegram asked for; sendMessage: 1 s.
    assert sleeps == [1, 2, 7, 1]
    assert fake.offsets() == [None, None, None, None, 2]
    assert fake.sent() == [{"chat_id": CHAT, "text": "eco: oi"}] * 2


def test_backoff_doubles_up_to_the_maximum() -> None:
    delays = Backoff(1, 10).delays()
    assert [next(delays) for _ in range(6)] == [1, 2, 4, 8, 10, 10]


def test_a_reply_that_cannot_be_sent_does_not_stop_the_loop(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeTelegram(
        updates=[[text_update(1, "oi"), text_update(2, "de novo")]],
        sends=[failure(403, "Forbidden: bot was blocked by the user")],
    )

    run_poll(fake, echo)

    assert len(fake.sent()) == 2
    assert "TelegramError" in caplog.text


def test_unreadable_updates_are_skipped_but_confirmed() -> None:
    received: list[IncomingMessage] = []

    def record(message: IncomingMessage) -> None:
        received.append(message)

    fake = FakeTelegram(
        updates=[
            [
                {"update_id": 5, "edited_message": {"text": "x"}},
                {"update_id": 6, "message": {"chat": "não é um chat"}},
                {"no_id": True},
                text_update(7, "oi", chat_type="group"),
            ]
        ]
    )

    run_poll(fake, record)

    # Only the real message reaches the bot, which decides about groups (it ignores them).
    assert received == [IncomingMessage(CHAT, "group", "oi")]
    assert fake.sent() == []
    assert fake.offsets()[-1] == 8


def test_a_crashing_handler_gets_a_generic_reply_and_no_details_in_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def crash(message: IncomingMessage) -> str:
        raise RuntimeError(f"falhou com {message.text}")

    fake = FakeTelegram(updates=[[text_update(1, "32,90 almoço")]])

    run_poll(fake, crash)

    assert fake.sent() == [{"chat_id": CHAT, "text": replies.SOMETHING_WENT_WRONG}]
    assert "RuntimeError" in caplog.text
    assert "almoço" not in caplog.text


def test_stopping_confirms_what_was_already_handled() -> None:
    fake = FakeTelegram(updates=[[text_update(30, "oi")]])
    fake.hang_when_empty = True

    async def scenario() -> None:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(fake)) as http:
            task = asyncio.create_task(poll(TelegramClient(TOKEN, http), echo))
            await fake.waiting.wait()
            task.cancel()  # what Ctrl+C does to asyncio.run's main task
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(scenario())

    method, payload = fake.calls[-1]
    assert method == "getUpdates"
    assert (payload["offset"], payload["timeout"], payload["limit"]) == (31, 0, 1)


def test_a_failed_confirmation_at_shutdown_is_only_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeTelegram(updates=[[text_update(30, "oi")]])
    fake.hang_when_empty = True

    async def scenario() -> None:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(fake)) as http:
            task = asyncio.create_task(poll(TelegramClient(TOKEN, http), echo))
            await fake.waiting.wait()
            fake.updates.append(failure(502, "Bad Gateway"))  # the confirmation fails
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(scenario())

    assert "confirmar" in caplog.text


def test_a_refused_request_is_raised_without_retrying() -> None:
    fake = FakeTelegram(updates=[failure(401, "Unauthorized")])

    with pytest.raises(TelegramError) as error:
        run_poll(fake, echo)

    assert error.value.status == 401
    assert len(fake.calls) == 1


def test_send_message_gives_up_after_four_attempts() -> None:
    fake = FakeTelegram(sends=[failure(500, "erro")] * 4)

    async def scenario() -> None:
        async def no_wait(_: float) -> None:
            return None

        async with httpx2.AsyncClient(transport=httpx2.MockTransport(fake)) as http:
            client = TelegramClient(TOKEN, http, sleep=no_wait)
            await client.send_message(CHAT, "x" * 5000)

    with pytest.raises(TelegramUnavailableError):
        asyncio.run(scenario())
    assert len(fake.sent()) == 4
    assert len(fake.sent()[0]["text"]) == 4096


def test_responses_that_are_not_json_are_retried() -> None:
    fake = FakeTelegram(updates=[httpx2.Response(502, text="<html>proxy</html>"), []])
    sleeps: list[float] = []

    run_poll(fake, echo, sleeps)

    assert sleeps == [1]


def test_the_token_is_only_in_the_url_and_never_in_repr() -> None:
    fake = FakeTelegram(updates=[[]])

    run_poll(fake, echo)

    assert fake.urls[0] == f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    assert TOKEN not in repr(TelegramClient(TOKEN, httpx2.AsyncClient()))
    assert Update.model_validate({"update_id": 1}).message is None


# ---------- The whole bot: fake Telegram + real database ----------


def test_the_bot_turns_a_message_into_a_transaction(
    settings: Settings,
    session: Session,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caplog.set_level(logging.INFO)
    monkeypatch.setattr("financas.telegram.bot.utc_now", lambda: NOW)  # the bot's clock
    user = create_user(session, "ana@example.com", "senha-segura-1")
    code, _ = issue_pairing_code(session, user, NOW)
    fake = FakeTelegram(
        updates=[
            [text_update(1, "oi")],
            [text_update(2, f"/conectar {code}"), text_update(3, "32,90 almoço ontem")],
        ]
    )

    asyncio.run(
        telegram_bot.run(
            TOKEN, settings, session_factory, transport=httpx2.MockTransport(fake), stop=fake.stop
        )
    )

    replies_sent = [payload["text"] for payload in fake.sent()]
    assert replies_sent[0] == replies.NOT_LINKED
    assert replies_sent[1].startswith("Pronto, este chat está conectado.")
    assert replies_sent[2].startswith("Anotado:")
    session.expire_all()
    (transaction,) = session.scalars(select(Transaction))
    assert (transaction.description, transaction.amount_cents, transaction.origin) == (
        "almoço",
        -3290,
        Origin.TELEGRAM,
    )
    assert transaction.date.isoformat() == "2026-11-07"
    assert session.get(User, user.id).telegram_chat_id == CHAT  # type: ignore[union-attr]
    # Logs say what happened, never what was written, how much, or the token.
    assert "@financas_teste_bot" in caplog.text
    for secret in (TOKEN, "SEGREDO", "almoço", "32,90", code, str(CHAT)):
        assert secret not in caplog.text


def fake_run(error: BaseException) -> Callable[..., Coroutine[Any, Any, None]]:
    async def run(*_: object, **__: object) -> None:
        raise error

    return run


def test_main_needs_a_token(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(telegram_bot, "get_settings", lambda: settings)

    assert telegram_bot.main() == telegram_bot.EXIT_NO_TOKEN
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("error", "exit_code", "message"),
    [
        (TelegramError(401, "Unauthorized"), 1, "recusou o token"),
        (TelegramError(409, "Conflict"), 1, "outro processo"),
        (TelegramError(400, "Bad Request"), 1, "HTTP 400"),
        (KeyboardInterrupt(), 0, "Bot parado"),
    ],
)
def test_main_explains_how_it_stopped(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: BaseException,
    exit_code: int,
    message: str,
) -> None:
    caplog.set_level(logging.INFO)
    with_token = settings.model_copy(update={"telegram_bot_token": SecretStr(TOKEN)})
    monkeypatch.setattr(telegram_bot, "get_settings", lambda: with_token)
    monkeypatch.setattr(telegram_bot, "run", fake_run(error))

    assert telegram_bot.main() == exit_code
    assert message in caplog.text
