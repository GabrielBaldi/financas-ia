"""A tolerant OFX reader.

Brazilian banks usually export OFX 1.x, which is SGML: value tags are often left unclosed and
the file is frequently Latin-1. Only the <STMTTRN> blocks matter here, so a few regular
expressions are easier to reason about than a strict parser that rejects half the real files.
"""

import datetime as dt
import re

from financas.importers.types import ParsedRow, ParsedStatement, StatementError, StatementFormat
from financas.importers.values import parse_amount

_TRANSACTION = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.IGNORECASE | re.DOTALL)


def looks_like_ofx(text: str) -> bool:
    head = text.lstrip()[:2000].upper()
    return head.startswith("OFXHEADER") or "<OFX>" in head


def _field(block: str, tag: str) -> str | None:
    # The value runs until the next tag or line break, whether or not the tag is closed.
    match = re.search(rf"<{tag}>\s*([^<\r\n]+)", block, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _parse_transaction(block: str) -> ParsedRow:
    posted = _field(block, "DTPOSTED")
    amount = _field(block, "TRNAMT")
    description = _field(block, "MEMO") or _field(block, "NAME")
    if not posted or not amount or not description:
        raise ValueError("transação sem data, valor ou descrição")
    try:
        date = dt.datetime.strptime(posted[:8], "%Y%m%d").date()
    except ValueError:
        raise ValueError(f"data inválida: '{posted}'") from None
    decimal_separator = "," if "," in amount and "." not in amount else "."
    return ParsedRow(date, description, parse_amount(amount, decimal_separator))


def parse_ofx(text: str) -> ParsedStatement:
    rows: list[ParsedRow] = []
    for number, match in enumerate(_TRANSACTION.finditer(text), start=1):
        try:
            rows.append(_parse_transaction(match.group(1)))
        except ValueError as error:
            raise StatementError(f"Transação {number} do OFX: {error}.") from None
    return ParsedStatement(StatementFormat.OFX, rows)
