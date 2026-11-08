"""Create the demo user with three months of fictional transactions.

Run with `uv run python -m financas.seed`. It is idempotent: the demo user is deleted and
created again. Rows go through the same import service as a real upload (rules only, no AI),
so the demo shows what the pipeline really does, including what is left "A revisar".
"""

import calendar
import datetime as dt
import random

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from financas.categories import Category
from financas.categorization.pipeline import Categorizer
from financas.config import get_settings
from financas.db import make_engine, make_session_factory
from financas.importers import ParsedRow, StatementFormat
from financas.models import Rule, Transaction, User
from financas.services.auth import create_user
from financas.services.imports import AIPricing, import_rows
from financas.services.months import month_bounds, month_of, recent_months, shift_month

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo1234"  # noqa: S105 (public demo account, shown on the login screen)
DEMO_ACCOUNT = "Conta Nubank"
SEED_MONTHS = 3

# Rules the demo user "already taught" the app.
DEMO_RULES = (
    ("bistro da vila", Category.ALIMENTACAO),
    ("associacao cultural aurora", Category.EDUCACAO),
)

# (day of the month, description, amount in cents: negative = money out)
MONTHLY: tuple[tuple[int, str, int], ...] = (
    (5, "Pagamento de salário - Tech Exemplo Ltda", 650_000),
    (6, "Aplicação RDB", -80_000),
    (8, "Pagamento de boleto efetuado - Lar Exemplo Imobiliária - Aluguel", -180_000),
    (10, "Pagamento de boleto efetuado - Condomínio Residencial Jardim", -52_000),
    (15, "Compra no débito - Vivo Fibra", -9_990),
    (16, "Compra no débito - Netflix.com", -3_990),
    (17, "Compra no débito - Spotify", -2_190),
    (18, "Compra no débito - Smart Fit", -11_990),
    (20, "Compra no débito - Alura", -10_900),
    (22, "Pagamento de boleto efetuado - Associação Cultural Aurora", -18_000),
)

# (description, times per month (min, max), amount range in cents)
VARIABLE: tuple[tuple[str, tuple[int, int], tuple[int, int]], ...] = (
    ("Débito automático - Enel Distribuição SP", (1, 1), (-19_000, -11_000)),
    ("Débito automático - Sabesp", (1, 1), (-9_800, -6_500)),
    ("Compra no débito - Supermercado Bom Preço", (3, 5), (-42_000, -12_000)),
    ("Compra no débito - Atacadão", (1, 1), (-48_000, -25_000)),
    ("Compra no débito via NuPay - iFood", (4, 8), (-9_500, -3_200)),
    ("Compra no débito - Uber *Trip", (6, 10), (-4_800, -1_200)),
    ("Compra no débito - 99app *99pop", (2, 4), (-3_500, -1_000)),
    ("Compra no débito - Padaria Pão Quente", (4, 8), (-3_200, -800)),
    ("Compra no débito - Auto Posto Shell", (1, 2), (-26_000, -15_000)),
    ("Compra no débito - Drogasil", (1, 2), (-12_000, -2_500)),
    ("Compra no débito - Mercadolivre*Loja", (0, 2), (-22_000, -4_000)),
    ("Compra no débito - Cinemark", (0, 1), (-9_000, -4_000)),
    ("Compra no débito - EC *Bistro da Vila", (1, 2), (-14_000, -6_000)),
    ("Transferência enviada pelo Pix - Ana Exemplo", (1, 2), (-20_000, -5_000)),
    ("Transferência recebida pelo Pix - Carlos Exemplo", (0, 1), (5_000, 15_000)),
    # Descriptions no rule knows: without AI they wait in "A revisar".
    ("Compra no débito - MP *Lojadoze", (0, 1), (-9_000, -3_000)),
    ("Compra no débito - SumUp *Recanto Verde", (1, 1), (-6_000, -1_500)),
    ("Compra no débito - PAG*JoaoExemplo", (0, 1), (-15_000, -4_000)),
)


def demo_rows(month: str, rng: random.Random) -> list[ParsedRow]:
    start, _ = month_bounds(month)
    last_day = calendar.monthrange(start.year, start.month)[1]
    rows = [
        ParsedRow(start.replace(day=min(day, last_day)), description, amount)
        for day, description, amount in MONTHLY
    ]
    for description, (fewest, most), (low, high) in VARIABLE:
        for _ in range(rng.randint(fewest, most)):
            day = start.replace(day=rng.randint(1, last_day))
            rows.append(ParsedRow(day, description, rng.randint(low, high)))
    return sorted(rows, key=lambda row: row.date)


def seed_demo(session: Session, today: dt.date) -> User:
    session.execute(delete(User).where(User.email == DEMO_EMAIL))
    session.commit()
    user = create_user(session, DEMO_EMAIL, DEMO_PASSWORD)
    session.add_all(Rule(user_id=user.id, pattern=p, category=c) for p, c in DEMO_RULES)
    session.commit()

    rng = random.Random(2026)  # noqa: S311 (reproducible fake data, not security)
    rules_only = Categorizer(classifier=None)
    last_full_month = shift_month(month_of(today), -1)
    for month in recent_months(last_full_month, SEED_MONTHS):
        import_rows(
            session,
            user_id=user.id,
            account_name=DEMO_ACCOUNT,
            filename=f"extrato-{month}.csv",
            file_format=StatementFormat.NUBANK_ACCOUNT,
            rows=demo_rows(month, rng),
            categorizer=rules_only,
            pricing=AIPricing(0, 0),
        )
    return user


def main() -> None:
    engine = make_engine(get_settings().database_url)
    with make_session_factory(engine)() as session:
        user = seed_demo(session, dt.date.today())
        count = session.scalar(
            select(func.count(Transaction.id)).where(Transaction.user_id == user.id)
        )
    engine.dispose()
    print(f"Usuário demo pronto: {DEMO_EMAIL} / {DEMO_PASSWORD} ({count} transações).")


if __name__ == "__main__":
    main()
