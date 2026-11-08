import datetime as dt

import pytest

from financas.importers import ParsedRow, StatementError, StatementFormat, parse_statement
from financas.importers.values import parse_amount
from tests.helpers import SAMPLES


@pytest.mark.parametrize(
    ("text", "separator", "cents"),
    [
        ("1.234,56", ",", 123456),
        ("-45,90", ",", -4590),
        ("R$ 12,00", ",", 1200),
        ("1.000.000,01", ",", 100000001),
        ("1234.56", ".", 123456),
        ("-0.5", ".", -50),
        ("1,234.56", ".", 123456),
    ],
)
def test_parse_amount(text: str, separator: str, cents: int) -> None:
    assert parse_amount(text, separator) == cents


@pytest.mark.parametrize("text", ["abc", "12,345", "", "1,2,3"])
def test_parse_amount_rejects_garbage_and_fractions_of_a_cent(text: str) -> None:
    with pytest.raises(ValueError, match="valor inválido"):
        parse_amount(text, ",")


def test_nubank_card_csv_flips_the_sign_so_purchases_are_negative() -> None:
    statement = parse_statement((SAMPLES / "nubank-cartao.csv").read_bytes())

    assert statement.file_format is StatementFormat.NUBANK_CARD
    assert len(statement.rows) == 10
    assert statement.rows[0] == ParsedRow(dt.date(2026, 10, 2), "Ifd*Burger da Esquina", -5290)
    payment = next(row for row in statement.rows if row.description == "Pagamento recebido")
    assert payment.amount_cents == 125000


def test_nubank_account_csv_keeps_the_sign_and_reads_brazilian_dates() -> None:
    statement = parse_statement((SAMPLES / "nubank-conta.csv").read_bytes())

    assert statement.file_format is StatementFormat.NUBANK_ACCOUNT
    assert statement.rows[0] == ParsedRow(
        dt.date(2026, 10, 1), "Compra no débito - Padaria Pão Quente", -4590
    )
    assert statement.rows[1].amount_cents == 650000


def test_generic_csv_with_header_and_brazilian_amounts() -> None:
    statement = parse_statement((SAMPLES / "extrato-generico.csv").read_bytes())

    assert statement.file_format is StatementFormat.GENERIC_CSV
    assert statement.rows[0] == ParsedRow(dt.date(2026, 10, 2), "SUPERMERCADO BOM PRECO", -123456)
    assert statement.rows[-1].amount_cents == 650000


def test_generic_csv_without_header_in_latin1() -> None:
    content = "05/11/2026;PADARIA SÃO JOÃO;-12,50\n06/11/2026;FARMÁCIA;-30,00\n".encode("cp1252")

    statement = parse_statement(content)

    assert [row.description for row in statement.rows] == ["PADARIA SÃO JOÃO", "FARMÁCIA"]


def test_ofx_sgml_with_unclosed_tags_comma_decimals_and_latin1() -> None:
    statement = parse_statement((SAMPLES / "extrato.ofx").read_bytes())

    assert statement.file_format is StatementFormat.OFX
    assert len(statement.rows) == 6
    assert statement.rows[0] == ParsedRow(
        dt.date(2026, 10, 2), "COMPRA CARTAO - IFOOD *RESTAURANTE SABOR", -8990
    )
    assert (
        statement.rows[2].description == "COMPRA CARTAO - ATACADÃO SÃO JOSÉ"
    )  # MEMO wins over NAME
    assert statement.rows[3].amount_cents == -2750  # "-27,50"
    assert statement.rows[5].amount_cents == 35000


def test_ofx_in_xml_style_with_closed_tags() -> None:
    content = b"""<?xml version="1.0"?><OFX><BANKTRANLIST>
    <STMTTRN><TRNTYPE>DEBIT</TRNTYPE><DTPOSTED>20261103</DTPOSTED>
    <TRNAMT>-10.00</TRNAMT><NAME>Padaria</NAME></STMTTRN></BANKTRANLIST></OFX>"""

    statement = parse_statement(content)

    assert statement.rows == [ParsedRow(dt.date(2026, 11, 3), "Padaria", -1000)]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "vazio"),
        (b"nome,idade\nAna,30\n", "Formato não reconhecido"),
        (b"data;descricao;valor\n", "Nenhuma transação"),
        (b"data;descricao;valor\n31/02/2026;Padaria;-5,00\n", "Linha 2: data inválida"),
        (b"data;descricao;valor\n01/02/2026;Padaria;-5,00;extra\n", "Linha 2: esperava 3 colunas"),
        (b"<OFX><STMTTRN><DTPOSTED>20261101</STMTTRN></OFX>", "Transação 1 do OFX"),
    ],
)
def test_unreadable_files_get_a_clear_message(content: bytes, message: str) -> None:
    with pytest.raises(StatementError, match=message):
        parse_statement(content)
