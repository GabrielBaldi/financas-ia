"""The bot's conversation: pairing, commands and entries (no Telegram here, just messages)."""

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from financas.categories import Category, Source
from financas.categorization.ai import AIItem
from financas.categorization.pipeline import Categorizer
from financas.importers import ParsedRow
from financas.models import Origin, Rule, Transaction, User
from financas.services.accounts import (
    MANUAL_ACCOUNT_NAME,
    accounts_starting_with,
    get_or_create_account,
)
from financas.services.auth import create_user
from financas.services.imports import AIPricing, import_rows
from financas.services.telegram_link import issue_pairing_code, set_default_account
from financas.telegram import replies
from financas.telegram.bot import IncomingMessage, TelegramBot, split_command
from financas.telegram.replies import MINUS
from tests.helpers import FakeClassifier, FakeClock

CHAT = 777_000_111


def say(bot: TelegramBot, text: str | None, chat_id: int = CHAT, chat_type: str = "private") -> str:
    reply = bot.handle(IncomingMessage(chat_id, chat_type, text))
    assert reply is not None
    return reply


def new_user(session: Session, email: str = "ana@example.com") -> User:
    return create_user(session, email, "senha-segura-1")


def link(session: Session, bot: TelegramBot, clock: FakeClock, chat_id: int = CHAT) -> User:
    user = new_user(session)
    code, _ = issue_pairing_code(session, user, clock())
    assert say(bot, f"/conectar {code}", chat_id).startswith("Pronto")
    session.refresh(user)
    return user


def transactions(session: Session) -> list[Transaction]:
    session.expire_all()
    return list(session.scalars(select(Transaction).order_by(Transaction.id)))


# ---------- Pairing ----------


def test_a_valid_code_links_the_chat_once(
    session: Session, bot: TelegramBot, clock: FakeClock
) -> None:
    user = new_user(session)
    code, expires_at = issue_pairing_code(session, user, clock())
    assert len(code) == 6 and code.isdigit()
    assert expires_at == clock() + dt.timedelta(minutes=10)

    reply = say(bot, f"/conectar {code}")

    assert "conectado" in reply and MANUAL_ACCOUNT_NAME in reply
    session.refresh(user)
    assert (user.telegram_chat_id, user.telegram_linked_at) == (CHAT, clock())
    assert user.telegram_pairing_code_hash is None  # single use
    # The same code from another chat is now just a wrong code.
    assert say(bot, f"/conectar {code}", chat_id=CHAT + 1) == replies.WRONG_CODE


def test_an_expired_code_is_refused(session: Session, bot: TelegramBot, clock: FakeClock) -> None:
    code, _ = issue_pairing_code(session, new_user(session), clock())
    clock.advance(minutes=10, seconds=1)

    assert say(bot, f"/conectar {code}") == replies.WRONG_CODE


def test_a_new_code_replaces_the_previous_one(
    session: Session, bot: TelegramBot, clock: FakeClock
) -> None:
    user = new_user(session)
    first, _ = issue_pairing_code(session, user, clock())
    second, _ = issue_pairing_code(session, user, clock())

    if first != second:
        assert say(bot, f"/conectar {first}") == replies.WRONG_CODE
    assert say(bot, f"/conectar {second}").startswith("Pronto")


def test_five_wrong_codes_lock_the_chat_for_15_minutes(
    session: Session, bot: TelegramBot, clock: FakeClock
) -> None:
    user = new_user(session)
    code, _ = issue_pairing_code(session, user, clock())
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(4):
        assert say(bot, f"/conectar {wrong}") == replies.WRONG_CODE
    assert say(bot, "/conectar abc") == replies.LOCKED_OUT  # malformed codes count too

    # Locked: even the right code and plain messages get no answer.
    assert bot.handle(IncomingMessage(CHAT, "private", f"/conectar {code}")) is None
    assert bot.handle(IncomingMessage(CHAT, "private", "oi")) is None
    # Other chats are not affected.
    assert say(bot, "oi", chat_id=CHAT + 1) == replies.NOT_LINKED

    clock.advance(minutes=14, seconds=59)
    assert bot.handle(IncomingMessage(CHAT, "private", "oi")) is None
    clock.advance(seconds=2)
    fresh, _ = issue_pairing_code(session, user, clock())  # the first one expired meanwhile
    assert say(bot, f"/conectar {fresh}").startswith("Pronto")


def test_old_mistakes_are_forgiven(session: Session, bot: TelegramBot, clock: FakeClock) -> None:
    issue_pairing_code(session, new_user(session), clock())
    for _ in range(4):
        say(bot, "/conectar 999999")
    clock.advance(minutes=16)

    assert say(bot, "/conectar 999999") == replies.WRONG_CODE  # counting starts again


def test_conectar_without_a_code_explains_itself(bot: TelegramBot) -> None:
    assert say(bot, "/conectar") == replies.CONNECT_USAGE


def test_linking_moves_the_chat_between_users(
    session: Session, bot: TelegramBot, clock: FakeClock
) -> None:
    first = link(session, bot, clock)
    second = new_user(session, "bia@example.com")
    code, _ = issue_pairing_code(session, second, clock())

    say(bot, f"/conectar {code}")

    session.refresh(first)
    session.refresh(second)
    assert (first.telegram_chat_id, second.telegram_chat_id) == (None, CHAT)


def test_desconectar_unlinks(session: Session, bot: TelegramBot, clock: FakeClock) -> None:
    user = link(session, bot, clock)

    assert say(bot, "/desconectar") == replies.UNLINKED

    session.refresh(user)
    assert user.telegram_chat_id is None
    assert say(bot, "32,90 almoço") == replies.NOT_LINKED


# ---------- Who gets an answer ----------


def test_an_unlinked_chat_cannot_create_entries(session: Session, bot: TelegramBot) -> None:
    new_user(session)

    for text in ("32,90 almoço", "/start", "/desfazer", "/ultimos", None):
        assert say(bot, text) == replies.NOT_LINKED
    assert transactions(session) == []


def test_groups_channels_and_bots_are_ignored(
    session: Session, bot: TelegramBot, clock: FakeClock
) -> None:
    link(session, bot, clock)

    assert bot.handle(IncomingMessage(CHAT, "group", "32,90 almoço")) is None
    assert bot.handle(IncomingMessage(CHAT, "channel", "32,90 almoço")) is None
    assert bot.handle(IncomingMessage(CHAT, "private", "32,90 almoço", from_bot=True)) is None
    assert transactions(session) == []


def test_commands_ignore_case_and_bot_mentions() -> None:
    assert split_command("/Conta@financas_bot  Nubank ") == ("/conta", "Nubank")
    assert split_command("32,90 almoço") == (None, "32,90 almoço")


# ---------- Entries ----------


def test_an_entry_goes_through_the_categorization_pipeline(
    session: Session, bot: TelegramBot, clock: FakeClock, fake_ai: FakeClassifier
) -> None:
    user = link(session, bot, clock)
    session.add(Rule(user_id=user.id, pattern="cantina do porto", category=Category.LAZER))
    session.commit()
    fake_ai.answers["almoço"] = (Category.ALIMENTACAO, 0.92)

    by_rule = say(bot, "cantina do porto 40")
    by_keyword = say(bot, "uber 23 ontem")
    by_ai = say(bot, "32,90 almoço")
    to_review = say(bot, "presente 50")

    assert "Lazer (sua regra)" in by_rule
    assert "Transporte (regra padrão)" in by_keyword
    assert "Alimentação (IA, 92%)" in by_ai
    assert "Categoria: a revisar" in to_review
    # Only what the rules could not decide reaches the AI, one entry at a time.
    assert fake_ai.batches == [[AIItem(0, "almoço", -3290)], [AIItem(0, "presente", -5000)]]

    rows = transactions(session)
    assert [(t.description, t.amount_cents, t.categorized_by) for t in rows] == [
        ("cantina do porto", -4000, Source.USER_RULE),
        ("uber", -2300, Source.KEYWORD),
        ("almoço", -3290, Source.AI),
        ("presente", -5000, Source.REVIEW),
    ]
    assert {t.origin for t in rows} == {Origin.TELEGRAM}
    assert rows[1].date.isoformat() == "2026-11-07"
    assert all(t.dedup_hash.startswith("telegram:") for t in rows)
    assert len({t.dedup_hash for t in rows}) == 4


def test_the_reply_has_amount_account_date_and_undo_hint(
    session: Session, bot: TelegramBot, clock: FakeClock
) -> None:
    link(session, bot, clock)

    reply = say(bot, "R$ 1.234,56 aluguel")

    assert reply == (
        f"Anotado: {MINUS}R$ 1.234,56 · aluguel\n"
        "Categoria: Moradia (regra padrão)\n"
        f"Conta: {MANUAL_ACCOUNT_NAME} · 08/11/2026\n"
        "Errou? /desfazer"
    )
    assert "Anotado: +R$ 50,00 · pix recebido" in say(bot, "+50 pix recebido")


def test_parse_errors_are_answered_with_examples(
    session: Session, bot: TelegramBot, clock: FakeClock
) -> None:
    link(session, bot, clock)

    assert "Não achei o valor" in say(bot, "almoço")
    assert say(bot, None) == replies.TEXT_ONLY
    assert say(bot, "/oi") == replies.UNKNOWN_COMMAND
    assert transactions(session) == []


def test_entries_use_the_default_account_or_a_hashtag(
    session: Session, bot: TelegramBot, clock: FakeClock
) -> None:
    user = link(session, bot, clock)
    card = get_or_create_account(session, user.id, "Cartão Nubank")
    get_or_create_account(session, user.id, "Conta Nubank")
    get_or_create_account(session, user.id, "Conta Inter")
    set_default_account(session, user, card)

    assert "Conta: Cartão Nubank" in say(bot, "uber 23")
    assert "Conta: Conta Inter" in say(bot, "uber 24 #inter")  # the start of a word
    assert "Conta: Conta Nubank" in say(bot, "uber 25 #conta_n")  # '_' stands for a space
    assert "Mais de uma conta com “nubank” no nome" in say(bot, "uber 26 #nubank")
    assert "Nenhuma conta com “itau” no nome" in say(bot, "uber 27 #itau")
    assert len(transactions(session)) == 3


def test_account_names_match_exactly_then_by_start_then_by_word(session: Session) -> None:
    user = new_user(session)
    for name in ("Inter", "Conta Inter", "Interbank", "Cartão Nubank"):
        get_or_create_account(session, user.id, name)

    def names(query: str) -> list[str]:
        return [account.name for account in accounts_starting_with(session, user.id, query)]

    assert names("inter") == ["Inter"]
    assert names("inte") == ["Inter", "Interbank"]
    assert names("nu") == ["Cartão Nubank"]
    assert names("cartão_nu") == ["Cartão Nubank"]
    assert names("bank") == []  # inside a word does not count
    assert names("!!") == []


def test_conta_shows_and_changes_the_default(
    session: Session, bot: TelegramBot, clock: FakeClock
) -> None:
    user = link(session, bot, clock)
    get_or_create_account(session, user.id, "Cartão Nubank")
    session.commit()

    assert "Sem conta padrão" in say(bot, "/conta")
    assert say(bot, "/conta cartao") == "Conta padrão agora é Cartão Nubank."
    assert say(bot, "/conta").startswith("Conta padrão: Cartão Nubank.")
    assert "Nenhuma conta com “xp” no nome" in say(bot, "/conta xp")
    session.refresh(user)
    assert user.telegram_default_account_id is not None


def test_desfazer_removes_the_last_pending_entry(
    session: Session, bot: TelegramBot, clock: FakeClock
) -> None:
    link(session, bot, clock)
    say(bot, "uber 23")
    say(bot, "padaria 8")

    assert say(bot, "/desfazer") == f"Apagado: {MINUS}R$ 8,00 · padaria (08/11/2026)."
    assert [t.description for t in transactions(session)] == ["uber"]
    say(bot, "/desfazer")
    assert say(bot, "/desfazer") == replies.NOTHING_TO_UNDO


def test_desfazer_never_touches_another_user(
    session: Session, bot: TelegramBot, clock: FakeClock
) -> None:
    link(session, bot, clock)
    other = new_user(session, "bia@example.com")
    code, _ = issue_pairing_code(session, other, clock())
    say(bot, f"/conectar {code}", chat_id=CHAT + 1)
    say(bot, "uber 23", chat_id=CHAT + 1)

    assert say(bot, "/desfazer") == replies.NOTHING_TO_UNDO
    assert len(transactions(session)) == 1


def test_ultimos_lists_the_latest_entries(
    session: Session, bot: TelegramBot, clock: FakeClock
) -> None:
    link(session, bot, clock)
    assert say(bot, "/ultimos") == replies.NO_ENTRIES
    for day in range(1, 8):
        say(bot, f"uber {day} 0{day}/11")

    lines = say(bot, "/ultimos").splitlines()

    assert lines[0] == "Últimos lançamentos:"
    assert len(lines) == 6
    assert lines[1] == f"07/11 · {MINUS}R$ 7,00 · uber · Transporte"


def test_help(session: Session, bot: TelegramBot, clock: FakeClock) -> None:
    link(session, bot, clock)
    assert say(bot, "/ajuda") == say(bot, "/start") == replies.HELP


@pytest.mark.parametrize(
    ("cents", "text"),
    [
        (0, "R$ 0,00"),
        (-5, f"{MINUS}R$ 0,05"),
        (123456, "+R$ 1.234,56"),
        (-100000000, f"{MINUS}R$ 1.000.000,00"),
    ],
)
def test_money_is_written_the_brazilian_way(cents: int, text: str) -> None:
    assert replies.money(cents) == text


def test_an_entry_already_in_the_statement_is_noted_there(
    session: Session, bot: TelegramBot, clock: FakeClock, categorizer: Categorizer
) -> None:
    user = link(session, bot, clock)
    import_rows(
        session,
        user_id=user.id,
        account_name="Cartão Nubank",
        filename="fatura.csv",
        file_format="csv_generico",
        rows=[ParsedRow(dt.date(2026, 11, 7), "PAG*PADARIAXYZ", -3290)],
        categorizer=categorizer,
        pricing=AIPricing(0, 0),
    )
    assert say(bot, "/conta cart") == "Conta padrão agora é Cartão Nubank."

    reply = say(bot, "32,90 padaria")

    assert reply.splitlines() == [
        f"Esse já estava no extrato: {MINUS}R$ 32,90 em 07/11/2026 (Cartão Nubank).",
        "Anotei “padaria” nele.",
        "Categoria: Alimentação (regra padrão)",
    ]
    assert "padaria · Alimentação · conferido no extrato" in say(bot, "/ultimos")
    assert say(bot, "/desfazer") == replies.NOTHING_TO_UNDO  # merged rows are the bank's


def test_conta_with_only_punctuation_matches_nothing(
    session: Session, bot: TelegramBot, clock: FakeClock
) -> None:
    link(session, bot, clock)
    assert say(bot, "/conta ???").startswith("Nenhuma conta com “???” no nome")
