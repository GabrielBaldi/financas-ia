"""CSV layouts: the two Nubank exports and a generic 'data;descrição;valor' file."""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass

from financas.importers.types import ParsedRow, ParsedStatement, StatementError, StatementFormat
from financas.importers.values import parse_amount, parse_br_date, parse_iso_date
from financas.text import normalize

type RowParser = Callable[[list[str]], ParsedRow]


def _nubank_card_row(cells: list[str]) -> ParsedRow:
    date, title, amount = cells
    # The card export lists purchases as positive numbers; flip so money out is negative.
    return ParsedRow(parse_iso_date(date), title.strip(), -parse_amount(amount, "."))


def _nubank_account_row(cells: list[str]) -> ParsedRow:
    date, amount, _identifier, description = cells
    return ParsedRow(parse_br_date(date), description.strip(), parse_amount(amount, "."))


def _generic_row(cells: list[str]) -> ParsedRow:
    date, description, amount = cells
    return ParsedRow(parse_br_date(date), description.strip(), parse_amount(amount, ","))


@dataclass(frozen=True, slots=True)
class _Layout:
    file_format: StatementFormat
    delimiter: str
    columns: int
    has_header: bool
    parse_row: RowParser


_NUBANK_CARD = _Layout(StatementFormat.NUBANK_CARD, ",", 3, True, _nubank_card_row)
_NUBANK_ACCOUNT = _Layout(StatementFormat.NUBANK_ACCOUNT, ",", 4, True, _nubank_account_row)


def _first_cells(first_line: str, delimiter: str) -> list[str]:
    return next(csv.reader([first_line], delimiter=delimiter))


def _looks_like_date(text: str) -> bool:
    try:
        parse_br_date(text)
    except ValueError:
        return False
    return True


def _detect_layout(first_line: str) -> _Layout:
    header = [normalize(cell) for cell in _first_cells(first_line, ",")]
    if header == ["date", "title", "amount"]:
        return _NUBANK_CARD
    if header == ["data", "valor", "identificador", "descricao"]:
        return _NUBANK_ACCOUNT

    cells = _first_cells(first_line, ";")
    if len(cells) == 3:
        has_header = not _looks_like_date(cells[0])
        return _Layout(StatementFormat.GENERIC_CSV, ";", 3, has_header, _generic_row)

    raise StatementError(
        "Formato não reconhecido. Envie um OFX, o CSV exportado pelo Nubank "
        "ou um CSV com as colunas data;descrição;valor."
    )


def parse_csv(text: str) -> ParsedStatement:
    first_line = next((line for line in text.splitlines() if line.strip()), None)
    if first_line is None:
        raise StatementError("O arquivo está vazio.")
    layout = _detect_layout(first_line)

    reader = csv.reader(io.StringIO(text), delimiter=layout.delimiter)
    rows: list[ParsedRow] = []
    header_pending = layout.has_header
    for cells in reader:
        if not any(cell.strip() for cell in cells):
            continue
        if header_pending:
            header_pending = False
            continue
        if len(cells) != layout.columns:
            expected, found = layout.columns, len(cells)
            raise StatementError(
                f"Linha {reader.line_num}: esperava {expected} colunas, encontrei {found}."
            )
        try:
            rows.append(layout.parse_row(cells))
        except ValueError as error:
            raise StatementError(f"Linha {reader.line_num}: {error}.") from None

    return ParsedStatement(layout.file_format, rows)
