"""Telegram entries and statement rows for the same purchase become one transaction."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from financas.categories import Category, Source
from financas.categorization.ai import AIItem
from financas.categorization.pipeline import Categorizer, Decision
from financas.importers import ParsedRow
from financas.models import Account, ImportBatch, Origin, Rule, Transaction, User
from financas.services.accounts import get_or_create_account
from financas.services.auth import create_user
from financas.services.imports import AIPricing, import_rows
from financas.services.manual_entries import EntryOutcome, ManualEntry, add_manual_entry
from financas.services.reconciliation import merged_decision
from financas.services.transactions import set_category
from tests.helpers import FakeClassifier, upload

CARD = "Cartão Nubank"


def nov(day: int) -> dt.date:
    return dt.date(2026, 11, day)


@pytest.fixture
def user(session: Session) -> User:
    return create_user(session, "ana@example.com", "senha-segura-1")


@pytest.fixture
def card(session: Session, user: User) -> Account:
    account = get_or_create_account(session, user.id, CARD)
    session.commit()
    return account


def entry(
    session: Session,
    user: User,
    categorizer: Categorizer,
    description: str,
    cents: int,
    day: dt.date,
    account: Account,
) -> EntryOutcome:
    return add_manual_entry(
        session,
        user=user,
        entry=ManualEntry(cents, description, day),
        categorizer=categorizer,
        account=account,
    )


def statement(
    session: Session,
    user: User,
    categorizer: Categorizer,
    rows: list[tuple[dt.date, str, int]],
    account_name: str = CARD,
) -> ImportBatch:
    return import_rows(
        session,
        user_id=user.id,
        account_name=account_name,
        filename="fatura.csv",
        file_format="csv_generico",
        rows=[ParsedRow(day, description, cents) for day, description, cents in rows],
        categorizer=categorizer,
        pricing=AIPricing(0, 0),
    )


def all_transactions(session: Session) -> list[Transaction]:
    session.expire_all()
    return list(session.scalars(select(Transaction).order_by(Transaction.date, Transaction.id)))


# ---------- On import: the statement row absorbs the entry ----------


def test_a_statement_row_absorbs_the_matching_entry(
    session: Session, user: User, card: Account, categorizer: Categorizer, fake_ai: FakeClassifier
) -> None:
    fake_ai.answers["almoço"] = (Category.ALIMENTACAO, 0.9)
    entry(session, user, categorizer, "almoço", -3290, nov(5), card)

    batch = statement(session, user, categorizer, [(nov(6), "PAG*RESTAURANTEXYZ", -3290)])

    assert batch.reconciled == 1
    (row,) = all_transactions(session)
    assert (row.date, row.description, row.note, row.origin) == (
        nov(6),
        "PAG*RESTAURANTEXYZ",
        "almoço",
        Origin.IMPORT,
    )
    assert (row.category, row.categorized_by, row.confidence) == (
        Category.ALIMENTACAO,
        Source.AI,
        0.9,
    )
    assert (batch.by_ai, batch.to_review) == (1, 0)
    # The bank's cryptic description never went to the AI: the entry already had an answer.
    assert fake_ai.batches == [[AIItem(0, "almoço", -3290)]]


def test_a_user_rule_on_the_statement_row_wins(
    session: Session, user: User, card: Account, categorizer: Categorizer, fake_ai: FakeClassifier
) -> None:
    session.add(Rule(user_id=user.id, pattern="restaurantexyz", category=Category.LAZER))
    fake_ai.answers["almoço"] = (Category.ALIMENTACAO, 0.9)
    entry(session, user, categorizer, "almoço", -3290, nov(5), card)

    statement(session, user, categorizer, [(nov(5), "PAG*RESTAURANTEXYZ", -3290)])

    (row,) = all_transactions(session)
    assert (row.category, row.categorized_by, row.note) == (
        Category.LAZER,
        Source.USER_RULE,
        "almoço",
    )


def test_an_uncategorized_entry_keeps_the_statement_category(
    session: Session, user: User, card: Account, categorizer: Categorizer
) -> None:
    entry(session, user, categorizer, "coisa", -2345, nov(5), card)

    statement(session, user, categorizer, [(nov(5), "UBER *TRIP", -2345)])

    (row,) = all_transactions(session)
    assert (row.category, row.categorized_by, row.note) == (
        Category.TRANSPORTE,
        Source.KEYWORD,
        "coisa",
    )


def test_a_manual_choice_on_the_entry_is_kept(
    session: Session, user: User, card: Account, categorizer: Categorizer
) -> None:
    session.add(Rule(user_id=user.id, pattern="restaurantexyz", category=Category.LAZER))
    outcome = entry(session, user, categorizer, "presente", -5000, nov(5), card)
    set_category(session, outcome.transaction, Category.COMPRAS)

    statement(session, user, categorizer, [(nov(5), "PAG*RESTAURANTEXYZ", -5000)])

    (row,) = all_transactions(session)
    assert (row.category, row.categorized_by) == (Category.COMPRAS, Source.MANUAL)


@pytest.mark.parametrize(
    ("row", "matches"),
    [
        ((nov(13), "X", -1000), True),  # 3 days later
        ((nov(7), "X", -1000), True),  # 3 days earlier
        ((nov(14), "X", -1000), False),  # 4 days: too far
        ((nov(10), "X", -1001), False),  # one cent off
        ((nov(10), "X", 1000), False),  # money in, not out
    ],
)
def test_same_amount_within_three_days(
    session: Session,
    user: User,
    card: Account,
    categorizer: Categorizer,
    row: tuple[dt.date, str, int],
    matches: bool,
) -> None:
    entry(session, user, categorizer, "café", -1000, nov(10), card)

    batch = statement(session, user, categorizer, [row])

    assert batch.reconciled == (1 if matches else 0)
    assert len(all_transactions(session)) == (1 if matches else 2)


def test_only_the_same_account(
    session: Session, user: User, card: Account, categorizer: Categorizer
) -> None:
    entry(session, user, categorizer, "café", -1000, nov(10), card)

    batch = statement(session, user, categorizer, [(nov(10), "X", -1000)], "Conta Inter")

    assert batch.reconciled == 0


def test_only_the_same_user(
    session: Session, user: User, card: Account, categorizer: Categorizer
) -> None:
    other = create_user(session, "bia@example.com", "senha-segura-1")
    entry(session, user, categorizer, "café", -1000, nov(10), card)

    batch = statement(session, other, categorizer, [(nov(10), "X", -1000)])

    assert batch.reconciled == 0


def test_closest_dates_pair_first_one_to_one(
    session: Session, user: User, card: Account, categorizer: Categorizer
) -> None:
    entry(session, user, categorizer, "primeiro", -2000, nov(3), card)
    entry(session, user, categorizer, "segundo", -2000, nov(5), card)

    batch = statement(
        session, user, categorizer, [(nov(4), "LOJA A", -2000), (nov(6), "LOJA B", -2000)]
    )

    # 04/11 is 1 day from both entries: the tie goes to the older entry (03/11),
    # and the other entry pairs with the row it is closest to among those left.
    assert batch.reconciled == 2
    assert [(t.description, t.note) for t in all_transactions(session)] == [
        ("LOJA A", "primeiro"),
        ("LOJA B", "segundo"),
    ]


def test_ties_on_the_same_day_go_to_the_entry_logged_first(
    session: Session, user: User, card: Account, categorizer: Categorizer
) -> None:
    entry(session, user, categorizer, "primeiro", -2000, nov(5), card)
    entry(session, user, categorizer, "segundo", -2000, nov(5), card)

    statement(session, user, categorizer, [(nov(5), "LOJA", -2000)])

    rows = all_transactions(session)
    assert [(t.origin, t.description, t.note) for t in rows] == [
        (Origin.TELEGRAM, "segundo", None),
        (Origin.IMPORT, "LOJA", "primeiro"),
    ]


def test_reimporting_the_statement_reconciles_nothing_new(
    session: Session, user: User, card: Account, categorizer: Categorizer
) -> None:
    entry(session, user, categorizer, "café", -1000, nov(10), card)
    statement(session, user, categorizer, [(nov(10), "PADARIA", -1000)])

    again = statement(session, user, categorizer, [(nov(10), "PADARIA", -1000)])

    assert (again.inserted, again.duplicates, again.reconciled) == (0, 1, 0)
    assert len(all_transactions(session)) == 1


# ---------- On entry: the statement already has it ----------


def test_an_entry_already_in_the_statement_becomes_its_note(
    session: Session, user: User, card: Account, categorizer: Categorizer, fake_ai: FakeClassifier
) -> None:
    statement(session, user, categorizer, [(nov(6), "PAG*RESTAURANTEXYZ", -3290)])
    fake_ai.answers["almoço"] = (Category.ALIMENTACAO, 0.9)

    outcome = entry(session, user, categorizer, "almoço", -3290, nov(7), card)

    assert outcome.already_in_statement
    (row,) = all_transactions(session)
    assert row.id == outcome.transaction.id
    assert (row.description, row.date, row.note, row.origin) == (
        "PAG*RESTAURANTEXYZ",
        nov(6),
        "almoço",
        Origin.IMPORT,
    )
    assert (row.category, row.categorized_by) == (Category.ALIMENTACAO, Source.AI)


def test_the_statement_category_stays_when_the_user_chose_it(
    session: Session, user: User, card: Account, categorizer: Categorizer, fake_ai: FakeClassifier
) -> None:
    statement(session, user, categorizer, [(nov(6), "PAG*RESTAURANTEXYZ", -3290)])
    (row,) = all_transactions(session)
    set_category(session, row, Category.LAZER)
    fake_ai.answers["almoço"] = (Category.ALIMENTACAO, 0.9)

    entry(session, user, categorizer, "almoço", -3290, nov(6), card)

    (row,) = all_transactions(session)
    assert (row.category, row.categorized_by, row.note) == (
        Category.LAZER,
        Source.MANUAL,
        "almoço",
    )
    assert fake_ai.batches == [[AIItem(0, "PAG*RESTAURANTEXYZ", -3290)]]  # import only


def test_the_closest_statement_row_is_noted_and_only_once(
    session: Session, user: User, card: Account, categorizer: Categorizer
) -> None:
    statement(
        session,
        user,
        categorizer,
        [(nov(4), "LOJA", -2000), (nov(6), "LOJA", -2000), (nov(9), "LOJA", -2000)],
    )

    first = entry(session, user, categorizer, "um", -2000, nov(5), card)  # tie: 04 and 06
    second = entry(session, user, categorizer, "dois", -2000, nov(5), card)  # 04 is taken
    third = entry(session, user, categorizer, "três", -2000, nov(5), card)  # 09 is 4 days away

    assert (first.transaction.date, second.transaction.date) == (nov(4), nov(6))
    assert not third.already_in_statement
    assert third.transaction.origin is Origin.TELEGRAM


# ---------- The rule itself ----------


AI_FOOD = Decision(Category.ALIMENTACAO, Source.AI, 0.9)
KEYWORD_TRANSPORT = Decision(Category.TRANSPORTE, Source.KEYWORD)
RULE_LEISURE = Decision(Category.LAZER, Source.USER_RULE)
MANUAL_SHOPPING = Decision(Category.COMPRAS, Source.MANUAL)
REVIEW = Decision(None, Source.REVIEW)


@pytest.mark.parametrize(
    ("statement_side", "entry_side", "winner"),
    [
        (KEYWORD_TRANSPORT, AI_FOOD, AI_FOOD),  # the user's words beat the bank's
        (REVIEW, AI_FOOD, AI_FOOD),
        (RULE_LEISURE, AI_FOOD, RULE_LEISURE),  # a user rule on the statement row stays
        (KEYWORD_TRANSPORT, REVIEW, KEYWORD_TRANSPORT),  # an empty answer changes nothing
        (MANUAL_SHOPPING, RULE_LEISURE, MANUAL_SHOPPING),  # manual choices always stay
        (RULE_LEISURE, MANUAL_SHOPPING, MANUAL_SHOPPING),
    ],
)
def test_merged_decision(statement_side: Decision, entry_side: Decision, winner: Decision) -> None:
    assert merged_decision(statement_side, entry_side) == winner


# ---------- Through the HTTP API ----------


def test_the_import_response_and_the_review_list_show_the_reconciliation(
    client: TestClient,
    headers: dict[str, str],
    session: Session,
    categorizer: Categorizer,
) -> None:
    user = session.scalars(select(User)).one()
    card = get_or_create_account(session, user.id, CARD)
    session.commit()
    entry(session, user, categorizer, "almoço com a equipe", -4590, nov(2), card)
    entry(session, user, categorizer, "uber", -1990, nov(2), card)

    summary = upload(
        client, headers, "data;descrição;valor\n03/11/2026;REST SABOR;-45,90\n", "fatura.csv", CARD
    )

    assert summary["reconciled"] == 1
    items = client.get("/transactions", headers=headers).json()["items"]
    assert [(t["description"], t["origin"], t["note"]) for t in items] == [
        ("REST SABOR", "import", "almoço com a equipe"),
        ("uber", "telegram", None),
    ]
