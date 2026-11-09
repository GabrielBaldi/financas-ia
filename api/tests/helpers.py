"""Shared test helpers: a fake AI classifier, a fake clock and shortcuts for the HTTP API."""

import datetime as dt
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from financas.categories import Category
from financas.categorization.ai import AIBatchResult, AIItem, AISuggestion, TokenUsage
from financas.config import Settings

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def make_settings(**values: Any) -> Settings:
    """Settings for a test: a developer's .env, AI keys and AI_PROVIDER never leak in."""
    isolated: dict[str, Any] = {
        "ai_provider": None,
        "anthropic_api_key": None,
        "nvidia_api_key": None,
    }
    return Settings(_env_file=None, **(isolated | values))


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


# 15:00 UTC is noon in São Paulo: "today" is 2026-11-08 for the bot.
NOW = dt.datetime(2026, 11, 8, 15, 0, tzinfo=dt.UTC)


class FakeClock:
    def __init__(self, now: dt.datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += dt.timedelta(**delta)


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
