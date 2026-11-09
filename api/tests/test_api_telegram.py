"""The web app's side of Telegram: status, pairing code, default account, unlink."""

import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from financas.models import User, utc_now
from financas.telegram import replies
from financas.telegram.bot import IncomingMessage, TelegramBot
from tests.helpers import FakeClock, register_and_login, upload

STATEMENT = "data;descrição;valor\n01/11/2026;Padaria;-12,00\n"


def test_status_starts_unlinked(client: TestClient, headers: dict[str, str]) -> None:
    response = client.get("/telegram", headers=headers)

    assert response.json() == {"linked": False, "linked_at": None, "default_account": None}


def test_the_pairing_code_links_the_chat(
    client: TestClient, headers: dict[str, str], bot: TelegramBot, clock: FakeClock
) -> None:
    created = client.post("/telegram/pairing-code", headers=headers)
    assert created.status_code == 201
    code = created.json()["code"]
    assert len(code) == 6 and code.isdigit()

    clock.now = utc_now()  # the API issued the code with the real clock
    reply = bot.handle(IncomingMessage(99, "private", f"/conectar {code}"))

    assert reply is not None and reply.startswith("Pronto")
    status = client.get("/telegram", headers=headers).json()
    assert status["linked"] is True
    assert status["linked_at"] is not None


def test_the_code_is_only_stored_as_a_hash(
    client: TestClient, headers: dict[str, str], session: Session
) -> None:
    code = client.post("/telegram/pairing-code", headers=headers).json()["code"]

    user = session.scalars(select(User)).one()
    assert user.telegram_pairing_code_hash == hashlib.sha256(code.encode()).hexdigest()


def test_unlink_stops_the_chat(
    client: TestClient, headers: dict[str, str], bot: TelegramBot, clock: FakeClock
) -> None:
    code = client.post("/telegram/pairing-code", headers=headers).json()["code"]
    clock.now = utc_now()
    bot.handle(IncomingMessage(99, "private", f"/conectar {code}"))

    assert client.delete("/telegram/link", headers=headers).status_code == 204

    assert client.get("/telegram", headers=headers).json()["linked"] is False
    assert bot.handle(IncomingMessage(99, "private", "32,90 almoço")) == replies.NOT_LINKED


def test_default_account_can_be_set_and_cleared(
    client: TestClient, headers: dict[str, str]
) -> None:
    upload(client, headers, STATEMENT, account="Cartão Nubank")
    accounts = client.get("/accounts", headers=headers).json()
    assert accounts == [{"id": 1, "name": "Cartão Nubank"}]

    chosen = client.put("/telegram/default-account", headers=headers, json={"account_id": 1})
    assert chosen.json()["default_account"] == {"id": 1, "name": "Cartão Nubank"}

    cleared = client.put("/telegram/default-account", headers=headers, json={"account_id": None})
    assert cleared.json()["default_account"] is None


def test_another_users_account_cannot_be_the_default(
    client: TestClient, headers: dict[str, str]
) -> None:
    upload(client, headers, STATEMENT, account="Cartão Nubank")
    other = register_and_login(client, "bia@example.com")

    response = client.put("/telegram/default-account", headers=other, json={"account_id": 1})

    assert response.status_code == 404
    assert client.get("/accounts", headers=other).json() == []


def test_everything_needs_a_login(client: TestClient) -> None:
    assert client.get("/telegram").status_code == 401
    assert client.post("/telegram/pairing-code").status_code == 401
    assert client.get("/accounts").status_code == 401
