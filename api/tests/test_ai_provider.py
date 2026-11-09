"""Which AI provider the settings pick, and the classifier and pricing the factory builds.

Only fake keys appear here, and no request is made: building a client sends nothing.
"""

import json
import logging
from functools import partial
from typing import Any

import httpx2
import pytest
from pydantic import ValidationError

from financas.categorization import factory
from financas.categorization.ai import AIItem, ClaudeClassifier
from financas.categorization.factory import (
    make_categorizer,
    make_classifier,
    make_pricing,
)
from financas.categorization.openai_compatible import OpenAICompatibleClassifier
from financas.config import Settings
from financas.services.imports import AIPricing
from tests.helpers import make_settings

ANTHROPIC_KEY = "sk-ant-chave-de-teste"
NVIDIA_KEY = "nvapi-chave-de-teste"


@pytest.mark.parametrize(
    ("values", "provider", "model"),
    [
        ({}, None, None),
        ({"anthropic_api_key": ANTHROPIC_KEY}, "anthropic", "claude-haiku-5-5"),
        ({"nvidia_api_key": NVIDIA_KEY}, "nvidia", "minimaxai/minimax-m3.1-flash"),
        # Both keys: Claude stays the default.
        (
            {"anthropic_api_key": ANTHROPIC_KEY, "nvidia_api_key": NVIDIA_KEY},
            "anthropic",
            "claude-haiku-5-5",
        ),
        # An explicit choice wins over the default.
        (
            {
                "ai_provider": "nvidia",
                "anthropic_api_key": ANTHROPIC_KEY,
                "nvidia_api_key": NVIDIA_KEY,
            },
            "nvidia",
            "minimaxai/minimax-m3.1-flash",
        ),
        ({"ai_provider": "anthropic", "ai_model": "claude-exemplo"}, "anthropic", "claude-exemplo"),
    ],
)
def test_the_provider_comes_from_the_keys_unless_chosen(
    values: dict[str, Any], provider: str | None, model: str | None
) -> None:
    settings = make_settings(**values)

    assert settings.ai_provider == provider
    assert settings.active_ai_model == model


def test_an_explicit_provider_without_its_key_turns_the_ai_off() -> None:
    """Never fall back to a provider nobody chose: the transactions would go somewhere else."""
    settings = make_settings(ai_provider="anthropic", nvidia_api_key=NVIDIA_KEY)

    assert settings.ai_provider == "anthropic"
    assert settings.ai_api_key is None
    assert not settings.ai_enabled


def test_ai_is_enabled_by_either_key() -> None:
    assert not make_settings().ai_enabled
    for keys in ({"anthropic_api_key": ANTHROPIC_KEY}, {"nvidia_api_key": NVIDIA_KEY}):
        settings = make_settings(**keys)
        assert settings.ai_enabled
        assert settings.ai_api_key is not None
        assert settings.ai_api_key.get_secret_value() in (ANTHROPIC_KEY, NVIDIA_KEY)


def test_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", ANTHROPIC_KEY)
    monkeypatch.setenv("NVIDIA_API_KEY", NVIDIA_KEY)
    monkeypatch.setenv("NVIDIA_MODEL", "exemplo/outro-modelo")
    monkeypatch.setenv("NVIDIA_BASE_URL", "https://nim.example.test/v1")
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("AI_PROVIDER", " NVIDIA ")  # case and spaces do not matter

    settings = Settings(_env_file=None)

    assert settings.ai_provider == "nvidia"
    assert settings.active_ai_model == "exemplo/outro-modelo"
    assert settings.nvidia_base_url == "https://nim.example.test/v1"
    assert settings.ai_timeout_seconds == 30


def test_blank_variables_mean_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """As copied from .env.example: AI_PROVIDER= and an empty key."""
    monkeypatch.setenv("AI_PROVIDER", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  ")
    monkeypatch.setenv("NVIDIA_API_KEY", NVIDIA_KEY)

    settings = Settings(_env_file=None)

    assert settings.anthropic_api_key is None
    assert settings.ai_provider == "nvidia"


@pytest.mark.parametrize(
    "values", [{"ai_provider": "openai"}, {"ai_timeout_seconds": 0}, {"ai_timeout_seconds": -5}]
)
def test_invalid_values_are_refused_at_start_up(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        make_settings(**values)


def test_keys_never_show_in_the_settings_repr() -> None:
    settings = make_settings(anthropic_api_key=ANTHROPIC_KEY, nvidia_api_key=NVIDIA_KEY)

    for text in (repr(settings), str(settings), settings.model_dump_json()):
        assert ANTHROPIC_KEY not in text
        assert NVIDIA_KEY not in text


def test_the_factory_builds_the_chosen_providers_classifier() -> None:
    assert make_classifier(make_settings()) is None
    assert isinstance(
        make_classifier(make_settings(anthropic_api_key=ANTHROPIC_KEY)), ClaudeClassifier
    )
    nvidia = make_classifier(make_settings(nvidia_api_key=NVIDIA_KEY))
    assert isinstance(nvidia, OpenAICompatibleClassifier)
    assert repr(nvidia) == (
        "OpenAICompatibleClassifier(provider='NVIDIA', model='minimaxai/minimax-m3.1-flash')"
    )


def test_the_categorizer_has_ai_with_either_key() -> None:
    assert not make_categorizer(make_settings()).ai_enabled
    assert make_categorizer(make_settings(anthropic_api_key=ANTHROPIC_KEY)).ai_enabled
    assert make_categorizer(make_settings(nvidia_api_key=NVIDIA_KEY)).ai_enabled


def test_the_nvidia_classifier_uses_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx2.Request] = []

    def fake_nvidia(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(503)

    monkeypatch.setattr(
        factory,
        "make_openai_compatible_classifier",
        partial(
            factory.make_openai_compatible_classifier, transport=httpx2.MockTransport(fake_nvidia)
        ),
    )
    settings = make_settings(
        nvidia_api_key=NVIDIA_KEY,
        nvidia_model="exemplo/outro-modelo",
        nvidia_base_url="https://nim.example.test/v1",
        ai_timeout_seconds=12,
    )
    classifier = make_classifier(settings)
    assert classifier is not None

    classifier.classify([AIItem(0, "PAG*JOSEEXEMPLO", -4500)])

    [request] = requests
    assert str(request.url) == "https://nim.example.test/v1/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {NVIDIA_KEY}"
    assert request.extensions["timeout"]["read"] == 12
    assert json.loads(request.content)["model"] == "exemplo/outro-modelo"


def test_a_chosen_provider_without_a_key_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        classifier = make_classifier(
            make_settings(ai_provider="nvidia", anthropic_api_key=ANTHROPIC_KEY)
        )

    assert classifier is None
    assert "AI_PROVIDER=nvidia, but NVIDIA_API_KEY is empty" in caplog.text
    assert ANTHROPIC_KEY not in caplog.text


def test_only_claude_is_priced() -> None:
    claude = make_settings(anthropic_api_key=ANTHROPIC_KEY, ai_input_price_per_mtok=1.0)

    assert make_pricing(claude) == AIPricing(1.0, 0.50)
    assert make_pricing(make_settings(nvidia_api_key=NVIDIA_KEY)) is None
    # Without a key nothing is spent; the fake classifier in tests is priced like Claude.
    assert make_pricing(make_settings()) == AIPricing(0.10, 0.50)
