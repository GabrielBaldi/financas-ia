"""Helpers for 'AAAA-MM' month strings, the unit of every filter and chart."""

import datetime as dt

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


def month_of(day: dt.date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def shift_month(month: str, delta: int) -> str:
    year, number = (int(part) for part in month.split("-"))
    index = year * 12 + (number - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_bounds(month: str) -> tuple[dt.date, dt.date]:
    """First day of the month and first day of the next one (half-open range)."""
    start = dt.date.fromisoformat(f"{month}-01")
    end = dt.date.fromisoformat(f"{shift_month(month, 1)}-01")
    return start, end


def recent_months(last: str, count: int) -> list[str]:
    """The `count` months ending at `last`, oldest first."""
    return [shift_month(last, offset) for offset in range(1 - count, 1)]
