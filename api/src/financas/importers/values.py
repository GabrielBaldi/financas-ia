import datetime as dt
from decimal import Decimal, InvalidOperation


def parse_amount(text: str, decimal_separator: str) -> int:
    """Parse '1.234,56' (separator ',') or '1234.56' (separator '.') into integer cents."""
    thousands_separator = "." if decimal_separator == "," else ","
    cleaned = text.strip().replace("R$", "").replace(" ", "").replace("\u00a0", "")
    cleaned = cleaned.replace(thousands_separator, "").replace(decimal_separator, ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"valor inválido: '{text}'") from None
    cents = value * 100
    if not cents.is_finite() or cents != cents.to_integral_value():
        raise ValueError(f"valor inválido: '{text}'")
    return int(cents)


def parse_br_date(text: str) -> dt.date:
    """Parse a 'dd/mm/aaaa' date."""
    try:
        return dt.datetime.strptime(text.strip(), "%d/%m/%Y").date()
    except ValueError:
        raise ValueError(f"data inválida: '{text}'") from None


def parse_iso_date(text: str) -> dt.date:
    try:
        return dt.date.fromisoformat(text.strip())
    except ValueError:
        raise ValueError(f"data inválida: '{text}'") from None
