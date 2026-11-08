"""Turn an uploaded bank statement (OFX or CSV) into a list of rows."""

from financas.importers.csv_formats import parse_csv
from financas.importers.ofx import looks_like_ofx, parse_ofx
from financas.importers.types import ParsedRow, ParsedStatement, StatementError, StatementFormat

__all__ = ["ParsedRow", "ParsedStatement", "StatementError", "StatementFormat", "parse_statement"]


def _decode(content: bytes) -> str:
    # Exports are UTF-8 (sometimes with a BOM) or, from older bank systems, Windows-1252.
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")


def parse_statement(content: bytes) -> ParsedStatement:
    """Detect the format from the content itself (not the file name) and parse it."""
    text = _decode(content)
    statement = parse_ofx(text) if looks_like_ofx(text) else parse_csv(text)
    if not statement.rows:
        raise StatementError("Nenhuma transação encontrada no arquivo.")
    return statement
