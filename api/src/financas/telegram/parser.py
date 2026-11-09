"""Read one entry typed in the chat: '32,90 almoço', 'uber 23 ontem', '+50 pix recebido #nubank'.

The words can come in any order. One number is the amount (Brazilian '1.234,56' or '32.90'),
an optional date word or dd/mm[/aaaa] is the day, an optional #tag names the account, and
everything else is the description, kept as typed. Amounts are expenses unless they start
with '+' or the message starts with 'recebi'.
"""

import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal

from financas.text import normalize

EXAMPLES = "32,90 almoço · uber 23 ontem · R$ 1.234,56 aluguel 05/11 · +50 pix recebido"

MAX_AMOUNT_CENTS = 1_000_000_000  # R$ 10 milhões: anything larger is a typo
MAX_DESCRIPTION = 255

_AMOUNT = re.compile(
    r"""
    (?P<sign>[+-])?
    (?P<currency>r\$)?
    (?P<number>
        \d{1,3}(?:\.\d{3})+(?:,\d{1,2})?  # 1.234 or 1.234,56: dots group thousands
      | \d{1,10}(?:[,.]\d{1,2})?          # 23, 32,90 or 32.90
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)
_THOUSANDS_ONLY = re.compile(r"\d{1,3}(?:\.\d{3})+")
_DATE = re.compile(r"(?P<day>\d{1,2})/(?P<month>\d{1,2})(?:/(?P<year>\d{4}|\d{2}))?")
_CURRENCY_GAP = re.compile(r"([+-]?r\$)\s+(?=\d)", re.IGNORECASE)  # 'R$ 10' -> 'R$10'

_EDGE_PUNCTUATION = " -:;,.\u2013\u2014"  # also the en and em dashes phones insert
_DAYS_AGO = {"hoje": 0, "ontem": 1, "anteontem": 2}
_INCOME_FIRST_WORDS = frozenset({"recebi"})
# 'dd/mm' without a year means this year, unless that is in the future and the same day last
# year was recent: '30/12' typed on January 2nd is three days ago, not next December.
_YEAR_WRAP = dt.timedelta(days=31)


class EntryParseError(ValueError):
    """The text is not an entry. The message is shown to the user as is (pt-BR)."""


@dataclass(frozen=True, slots=True)
class ParsedEntry:
    amount_cents: int  # negative = money out, like statement rows
    description: str
    date: dt.date
    account_hint: str | None  # the #tag without '#', matched against account names later


@dataclass(frozen=True, slots=True)
class _Amount:
    position: int
    cents: int
    sign: str | None
    explicit: bool  # had a sign, 'R$' or decimals: certainly money, not '2 cafés'


def _to_cents(number: str) -> int:
    if "," in number:
        text = number.replace(".", "").replace(",", ".")
    elif _THOUSANDS_ONLY.fullmatch(number):
        text = number.replace(".", "")
    else:
        text = number
    return int(Decimal(text) * 100)


def _read_amount(token: str, position: int) -> _Amount | None:
    match = _AMOUNT.fullmatch(token)
    if match is None:
        return None
    number = match["number"]
    explicit = bool(match["sign"] or match["currency"]) or bool(re.search(r"[,.]\d{1,2}$", number))
    return _Amount(position, _to_cents(number), match["sign"], explicit)


def _calendar_date(year: int, month: int, day: int, token: str) -> dt.date:
    try:
        return dt.date(year, month, day)
    except ValueError:
        raise EntryParseError(f"A data {token} não existe.") from None


def _read_date(token: str, today: dt.date) -> dt.date | None:
    """A date word or dd/mm[/aaaa]; None if the token is not a date at all."""
    if (days_ago := _DAYS_AGO.get(normalize(token))) is not None:
        return today - dt.timedelta(days=days_ago)
    match = _DATE.fullmatch(token)
    if match is None:
        return None
    day, month, year = int(match["day"]), int(match["month"]), match["year"]
    if year is not None:
        return _calendar_date(int(year) + (2000 if len(year) == 2 else 0), month, day, token)

    date = _calendar_date(today.year, month, day, token)
    if date > today:
        try:
            last_year = date.replace(year=today.year - 1)
        except ValueError:  # 29/02: the future-date check reports it
            return date
        if today - last_year <= _YEAR_WRAP:
            return last_year
    return date


def _pick_amount(amounts: list[_Amount]) -> _Amount:
    if not amounts:
        raise EntryParseError(f"Não achei o valor. Exemplos: {EXAMPLES}")
    if len(amounts) == 1:
        return amounts[0]
    explicit = [amount for amount in amounts if amount.explicit]
    if len(explicit) == 1:
        return explicit[0]
    raise EntryParseError(
        "Achei mais de um número e não sei qual é o valor. "
        "Escreva o valor com centavos (ex.: 2 cafés 10,00)."
    )


def parse_entry(text: str, today: dt.date) -> ParsedEntry:
    """Raises EntryParseError with a friendly message when the text is not an entry."""
    tokens = _CURRENCY_GAP.sub(r"\1", text.strip()).split()
    date: dt.date | None = None
    account_hint: str | None = None
    amounts: list[_Amount] = []
    kept: list[int] = []  # positions of the description words

    for position, token in enumerate(tokens):
        bare = token.rstrip(",;:.")
        if date is None and (found := _read_date(bare, today)) is not None:
            date = found
        elif account_hint is None and bare.startswith("#") and len(bare) > 1:
            account_hint = bare[1:]
        elif (amount := _read_amount(bare, position)) is not None:
            amounts.append(amount)
        else:
            kept.append(position)

    chosen = _pick_amount(amounts)
    kept = sorted(kept + [amount.position for amount in amounts if amount is not chosen])
    description = " ".join(tokens[position] for position in kept).strip(_EDGE_PUNCTUATION)
    if not description:
        raise EntryParseError(f"Faltou dizer com o quê. Exemplos: {EXAMPLES}")
    if chosen.cents <= 0:
        raise EntryParseError("O valor precisa ser maior que zero.")
    if chosen.cents > MAX_AMOUNT_CENTS:
        raise EntryParseError("Esse valor é alto demais para um lançamento.")
    date = date or today
    if date > today:
        raise EntryParseError("Essa data está no futuro. Lance o gasto no dia em que aconteceu.")

    income = chosen.sign == "+" or (
        chosen.sign is None and normalize(tokens[kept[0]]) in _INCOME_FIRST_WORDS
    )
    return ParsedEntry(
        amount_cents=chosen.cents if income else -chosen.cents,
        description=description[:MAX_DESCRIPTION],
        date=date,
        account_hint=account_hint,
    )
