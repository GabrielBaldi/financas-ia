import datetime as dt
from dataclasses import dataclass
from enum import StrEnum


class StatementFormat(StrEnum):
    OFX = "ofx"
    NUBANK_CARD = "nubank_cartao"
    NUBANK_ACCOUNT = "nubank_conta"
    GENERIC_CSV = "csv_generico"


@dataclass(frozen=True, slots=True)
class ParsedRow:
    date: dt.date
    description: str
    amount_cents: int  # negative = money out, positive = money in


@dataclass(frozen=True, slots=True)
class ParsedStatement:
    file_format: StatementFormat
    rows: list[ParsedRow]


class StatementError(ValueError):
    """The file could not be read as a statement. The message is shown to the user (pt-BR)."""
