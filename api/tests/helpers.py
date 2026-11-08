"""Shared test helpers: a fake AI classifier and shortcuts for the HTTP API."""

from collections.abc import Sequence
from pathlib import Path

from fastapi.testclient import TestClient

from financas.categories import Category
from financas.categorization.ai import AIBatchResult, AIItem, AISuggestion, TokenUsage

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


class FakeClassifier:
    """Stands in for Claude: answers from a description -> (category, confidence) table."""

    def __init__(self, answers: dict[str, tuple[Category, float]] | None = None) -> None:
        self.answers = answers or {}
        self.batches: list[list[AIItem]] = []

    def classify(self, items: Sequence[AIItem]) -> AIBatchResult:
        self.batches.append(list(items))
        suggestions = {}
        for item in items:
            if item.description in self.answers:
                category, confidence = self.answers[item.description]
                suggestions[item.id] = AISuggestion(
                    id=item.id, category=category, confidence=confidence
                )
        return AIBatchResult(suggestions, TokenUsage(100 * len(items), 20 * len(items)))


def login(client: TestClient, email: str, password: str = "senha-segura-1") -> dict[str, str]:
    response = client.post("/auth/token", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def register_and_login(client: TestClient, email: str = "ana@example.com") -> dict[str, str]:
    response = client.post("/auth/register", json={"email": email, "password": "senha-segura-1"})
    assert response.status_code == 201, response.text
    return login(client, email)


def upload(
    client: TestClient,
    headers: dict[str, str],
    content: str | bytes,
    filename: str = "extrato.csv",
    account: str = "Conta Nubank",
) -> dict[str, object]:
    data = content.encode() if isinstance(content, str) else content
    response = client.post(
        "/imports",
        headers=headers,
        files={"file": (filename, data, "text/csv")},
        data={"account_name": account},
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body
