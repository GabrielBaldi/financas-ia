"""The review flow: filter, correct a category, turn the correction into a rule."""

from typing import Any

from fastapi.testclient import TestClient

from tests.helpers import upload

STATEMENT = """data;descrição;valor
28/09/2026;EC *CANTINADOPORTO;-40,00
01/10/2026;Compra no débito - Padaria Pão Quente;-12,00
05/10/2026;EC *CANTINADOPORTO;-88,00
09/10/2026;EC *CANTINADOPORTO;-61,50
12/10/2026;MP *LOJADOZE;-39,90
"""


def transactions(
    client: TestClient, headers: dict[str, str], **params: str
) -> list[dict[str, Any]]:
    response = client.get("/transactions", headers=headers, params=params)
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def test_filters_by_month_category_and_to_review(
    client: TestClient, headers: dict[str, str]
) -> None:
    upload(client, headers, STATEMENT)

    october = transactions(client, headers, month="2026-10")
    assert [t["date"] for t in october] == ["2026-10-12", "2026-10-09", "2026-10-05", "2026-10-01"]

    food = transactions(client, headers, category="alimentacao")
    assert [t["categorized_by"] for t in food] == ["keyword"]

    to_review = transactions(client, headers, month="2026-10", to_review="true")
    assert len(to_review) == 3
    assert all(t["category"] is None for t in to_review)

    assert client.get("/transactions/months", headers=headers).json() == ["2026-10", "2026-09"]


def test_invalid_month_is_rejected(client: TestClient, headers: dict[str, str]) -> None:
    assert client.get("/transactions?month=2026-13", headers=headers).status_code == 422


def test_manual_correction_then_apply_to_similar(
    client: TestClient, headers: dict[str, str]
) -> None:
    upload(client, headers, STATEMENT)
    first, *others = [t for t in transactions(client, headers) if "CANTINA" in t["description"]]

    changed = client.patch(
        f"/transactions/{first['id']}", headers=headers, json={"category": "alimentacao"}
    ).json()
    assert (changed["category"], changed["categorized_by"]) == ("alimentacao", "manual")

    similar = client.get(f"/transactions/{first['id']}/similar", headers=headers).json()
    assert similar == {"pattern": "ec cantinadoporto", "count": 2}  # the manual one is not counted

    created = client.post(
        "/rules", headers=headers, json={"pattern": similar["pattern"], "category": "alimentacao"}
    )
    assert created.status_code == 201
    assert created.json()["applied"] == 2

    updated = {t["id"]: t for t in transactions(client, headers)}
    assert all(updated[t["id"]]["categorized_by"] == "user_rule" for t in others)
    assert updated[first["id"]]["categorized_by"] == "manual"


def test_rules_apply_to_future_imports_and_can_be_deleted(
    client: TestClient, headers: dict[str, str]
) -> None:
    rule = client.post(
        "/rules", headers=headers, json={"pattern": "MP *Lojadoze", "category": "compras"}
    ).json()["rule"]
    assert rule["pattern"] == "mp lojadoze"  # stored normalized

    summary = upload(client, headers, STATEMENT)
    assert summary["by_user_rule"] == 1

    assert client.delete(f"/rules/{rule['id']}", headers=headers).status_code == 204
    assert client.get("/rules", headers=headers).json() == []
    # Transactions keep the category they already had.
    assert transactions(client, headers, category="compras")[0]["categorized_by"] == "user_rule"


def test_saving_the_same_pattern_again_updates_the_rule(
    client: TestClient, headers: dict[str, str]
) -> None:
    upload(client, headers, STATEMENT)
    client.post("/rules", headers=headers, json={"pattern": "cantinadoporto", "category": "lazer"})

    again = client.post(
        "/rules", headers=headers, json={"pattern": "cantinadoporto", "category": "alimentacao"}
    ).json()

    assert again["applied"] == 3
    assert [r["category"] for r in client.get("/rules", headers=headers).json()] == ["alimentacao"]


def test_a_shorter_new_rule_does_not_override_a_more_specific_one(
    client: TestClient, headers: dict[str, str]
) -> None:
    upload(client, headers, STATEMENT)
    client.post(
        "/rules", headers=headers, json={"pattern": "ec cantinadoporto", "category": "lazer"}
    )

    broad = client.post(
        "/rules", headers=headers, json={"pattern": "cantinadoporto", "category": "compras"}
    )

    assert broad.json()["applied"] == 0
    assert len(transactions(client, headers, category="lazer")) == 3


def test_rule_pattern_must_have_three_real_characters(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.post("/rules", headers=headers, json={"pattern": "*-*", "category": "lazer"})

    assert response.status_code == 422
