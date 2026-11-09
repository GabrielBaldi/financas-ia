"""The app's clock for calendar days. Statements are Brazilian, so "today" is São Paulo's."""

import datetime as dt
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def local_today(now: dt.datetime) -> dt.date:
    """The calendar day in São Paulo at the (timezone-aware) instant `now`."""
    return now.astimezone(APP_TIMEZONE).date()
