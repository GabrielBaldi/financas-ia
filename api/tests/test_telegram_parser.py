"""The text of a Telegram message -> amount, description, date and account."""

import datetime as dt

import pytest

from financas.telegram.parser import EntryParseError, ParsedEntry, parse_entry

TODAY = dt.date(2026, 11, 8)


@pytest.mark.parametrize(
    ("text", "amount_cents", "description", "date"),
    [
        ("32,90 almoço", -3290, "almoço", TODAY),
        ("almoço 32,90", -3290, "almoço", TODAY),
        ("R$ 1.234,56 aluguel", -123456, "aluguel", TODAY),
        ("uber 23", -2300, "uber", TODAY),
        ("32.90 padaria", -3290, "padaria", TODAY),
        ("R$32 lanche", -3200, "lanche", TODAY),
        ("1.234 televisão", -123400, "televisão", TODAY),  # a dot before 3 digits groups them
        ("café 7,5", -750, "café", TODAY),
        ("-R$ 15 estacionamento", -1500, "estacionamento", TODAY),
        ("almoço: 32,90.", -3290, "almoço", TODAY),  # punctuation around the words is dropped
        ("99app 15", -1500, "99app", TODAY),  # digits glued to letters are part of the name
        ("2 cafés 10,00", -1000, "2 cafés", TODAY),  # the number with cents is the amount
        ("Pão de Açúcar 87,40", -8740, "Pão de Açúcar", TODAY),  # kept as typed
    ],
)
def test_amount_and_description_in_any_order(
    text: str, amount_cents: int, description: str, date: dt.date
) -> None:
    assert parse_entry(text, TODAY) == ParsedEntry(amount_cents, description, date, None)


@pytest.mark.parametrize(
    ("text", "date"),
    [
        ("hoje café 5", TODAY),
        ("almoço 32,90 ontem", dt.date(2026, 11, 7)),
        ("Anteontem uber 15", dt.date(2026, 11, 6)),
        ("05/11 padaria 5", dt.date(2026, 11, 5)),
        ("padaria 5 5/1", dt.date(2026, 1, 5)),
        ("padaria 5 05/11/2025", dt.date(2025, 11, 5)),
        ("padaria 5 05/11/25", dt.date(2025, 11, 5)),
    ],
)
def test_date_words_and_day_month(text: str, date: dt.date) -> None:
    assert parse_entry(text, TODAY).date == date


def test_day_month_from_late_december_typed_in_january_is_last_year() -> None:
    assert parse_entry("30/12 padaria 5", dt.date(2027, 1, 2)).date == dt.date(2026, 12, 30)


def test_a_future_29_february_is_refused_not_moved_to_a_year_without_it() -> None:
    with pytest.raises(EntryParseError, match="no futuro"):
        parse_entry("29/02 padaria 5", dt.date(2028, 1, 10))


@pytest.mark.parametrize(
    ("text", "amount_cents", "description"),
    [
        ("+50 pix recebido", 5000, "pix recebido"),
        ("recebi 50", 5000, "recebi"),
        ("Recebi 1.500,00 salário", 150000, "Recebi salário"),
        ("+R$ 20 reembolso", 2000, "reembolso"),
    ],
)
def test_income(text: str, amount_cents: int, description: str) -> None:
    entry = parse_entry(text, TODAY)
    assert (entry.amount_cents, entry.description) == (amount_cents, description)


@pytest.mark.parametrize(
    ("text", "hint", "description"),
    [
        ("mercado 150 #nubank", "nubank", "mercado"),
        ("#cartao_nubank mercado 150", "cartao_nubank", "mercado"),
        ("mercado 150 #inter.", "inter", "mercado"),
        ("mercado # 150", None, "mercado #"),  # a lone # is just text
    ],
)
def test_account_hashtag(text: str, hint: str | None, description: str) -> None:
    entry = parse_entry(text, TODAY)
    assert (entry.account_hint, entry.description) == (hint, description)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("almoço", "Não achei o valor"),
        ("", "Não achei o valor"),
        ("32,90", "Faltou dizer com o quê"),
        ("32,90 ontem #nubank", "Faltou dizer com o quê"),
        ("2 cafés 10", "mais de um número"),
        ("0 almoço", "maior que zero"),
        ("almoço 99999999,99", "alto demais"),
        ("almoço 10 31/02", "A data 31/02 não existe"),
        ("almoço 10 10/11", "no futuro"),
        ("almoço 10 01/01/2027", "no futuro"),
    ],
)
def test_clear_errors(text: str, message: str) -> None:
    with pytest.raises(EntryParseError, match=message):
        parse_entry(text, TODAY)


def test_errors_show_examples() -> None:
    with pytest.raises(EntryParseError, match="32,90 almoço"):
        parse_entry("almoço", TODAY)


def test_long_descriptions_are_cut_to_the_column_size() -> None:
    entry = parse_entry("10 " + "a" * 300, TODAY)
    assert len(entry.description) == 255
