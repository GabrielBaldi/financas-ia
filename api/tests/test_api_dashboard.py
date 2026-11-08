from fastapi.testclient import TestClient

from tests.helpers import upload

STATEMENT = """data;descrição;valor
05/10/2026;Pagamento de salário - Tech Exemplo;6.500,00
06/10/2026;Aplicação RDB;-500,00
08/10/2026;Supermercado Bom Preço;-300,00
09/10/2026;Atacadão;-200,00
10/10/2026;Pagamento de fatura;-1.250,00
11/10/2026;MP *LOJADOZE;-40,00
12/10/2026;Uber *Trip;-25,00
15/09/2026;Uber *Trip;-30,00
20/06/2026;Padaria Pão Quente;-10,00
20/04/2026;Padaria Pão Quente;-99,00
"""


def test_dashboard_for_a_month(client: TestClient, headers: dict[str, str]) -> None:
    upload(client, headers, STATEMENT)

    dashboard = client.get("/dashboard?month=2026-10", headers=headers).json()

    # Card bill and investment are moves between the user's own pockets: not counted.
    assert dashboard["expenses_cents"] == 30000 + 20000 + 4000 + 2500
    assert dashboard["income_cents"] == 650000
    assert dashboard["by_category"] == [
        {"category": "mercado", "total_cents": 50000},
        {"category": None, "total_cents": 4000},  # "A revisar" still shows up
        {"category": "transporte", "total_cents": 2500},
    ]
    assert dashboard["monthly"] == [
        {"month": "2026-05", "expenses_cents": 0, "income_cents": 0},
        {"month": "2026-06", "expenses_cents": 1000, "income_cents": 0},
        {"month": "2026-07", "expenses_cents": 0, "income_cents": 0},
        {"month": "2026-08", "expenses_cents": 0, "income_cents": 0},
        {"month": "2026-09", "expenses_cents": 3000, "income_cents": 0},
        {"month": "2026-10", "expenses_cents": 56500, "income_cents": 650000},
    ]


def test_dashboard_of_an_empty_month(client: TestClient, headers: dict[str, str]) -> None:
    dashboard = client.get("/dashboard?month=2027-01", headers=headers).json()

    assert dashboard["by_category"] == []
    assert dashboard["monthly"][0]["month"] == "2026-08"  # six months, crossing the year


def test_dashboard_requires_a_valid_month(client: TestClient, headers: dict[str, str]) -> None:
    assert client.get("/dashboard", headers=headers).status_code == 422
    assert client.get("/dashboard?month=10-2026", headers=headers).status_code == 422
