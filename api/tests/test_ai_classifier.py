"""ClaudeClassifier against a fake Anthropic client: the real API is never called in tests."""

import json
from typing import Any, cast

import anthropic
import httpx2
import pytest
from anthropic.types import Message

from financas.categories import Category
from financas.categorization.ai import (
    CATEGORY_HINTS,
    AIItem,
    ClaudeClassifier,
    TokenUsage,
)

ITEMS = [AIItem(0, "EC *CANTINADOPORTO", -8800), AIItem(1, "PAG*JOSEEXEMPLO", -4500)]


def message(text: str, stop_reason: str = "end_turn") -> Message:
    return Message.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-5-5",
            "content": [{"type": "text", "text": text}],
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 500, "output_tokens": 80},
        }
    )


class FakeMessages:
    def __init__(self, outcome: Message | Exception) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Message:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FakeAnthropic:
    def __init__(self, outcome: Message | Exception) -> None:
        self.messages = FakeMessages(outcome)


def classifier_for(outcome: Message | Exception) -> tuple[ClaudeClassifier, FakeMessages]:
    fake = FakeAnthropic(outcome)
    return ClaudeClassifier(cast(anthropic.Anthropic, fake), "claude-haiku-5-5"), fake.messages


def results(*items: dict[str, object]) -> str:
    return json.dumps({"results": list(items)})


def test_one_structured_request_for_the_whole_batch() -> None:
    answer = results(
        {"id": 0, "category": "alimentacao", "confidence": 0.92},
        {"id": 1, "category": "transferencias", "confidence": 0.4},
    )
    classifier, calls = classifier_for(message(answer))

    result = classifier.classify(ITEMS)

    assert len(calls.calls) == 1
    request = calls.calls[0]
    assert request["model"] == "claude-haiku-5-5"
    assert request["output_config"]["effort"] == "low"
    schema = request["output_config"]["format"]["schema"]
    category_enum = schema["properties"]["results"]["items"]["properties"]["category"]["enum"]
    assert set(category_enum) == {category.value for category in Category}
    assert (
        '"description": "EC *CANTINADOPORTO", "amount": "-88.00"'
        in request["messages"][0]["content"]
    )

    assert result.suggestions[0].category is Category.ALIMENTACAO
    assert result.suggestions[1].confidence == 0.4
    assert result.usage == TokenUsage(500, 80)


def test_invalid_items_are_dropped_one_by_one() -> None:
    answer = results(
        {"id": 0, "category": "categoria-inventada", "confidence": 0.9},
        {"id": 1, "category": "lazer", "confidence": 1.7},
        {"id": 7, "category": "lazer", "confidence": 0.9},  # an id we never sent
    )
    classifier, _ = classifier_for(message(answer))

    assert classifier.classify(ITEMS).suggestions == {}


def test_first_answer_wins_when_an_id_repeats() -> None:
    answer = results(
        {"id": 0, "category": "lazer", "confidence": 0.9},
        {"id": 0, "category": "compras", "confidence": 0.9},
    )
    classifier, _ = classifier_for(message(answer))

    assert classifier.classify(ITEMS).suggestions[0].category is Category.LAZER


@pytest.mark.parametrize(
    "outcome",
    [
        message("isto não é JSON"),
        message('{"results": [{"id": 0, "categ', stop_reason="max_tokens"),
        message("", stop_reason="refusal"),
    ],
)
def test_unusable_answers_send_everything_to_review(outcome: Message) -> None:
    classifier, _ = classifier_for(outcome)

    result = classifier.classify(ITEMS)

    assert result.suggestions == {}
    assert result.usage == TokenUsage(500, 80)  # the tokens were still spent


REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APIConnectionError(request=REQUEST),
        anthropic.RateLimitError(
            "rate limited", response=httpx2.Response(429, request=REQUEST), body=None
        ),
        anthropic.InternalServerError(
            "overloaded", response=httpx2.Response(529, request=REQUEST), body=None
        ),
    ],
)
def test_api_failures_do_not_break_the_import(error: Exception) -> None:
    classifier, _ = classifier_for(error)

    result = classifier.classify(ITEMS)

    assert result.suggestions == {}
    assert result.usage == TokenUsage()


def test_every_category_is_explained_to_the_model() -> None:
    assert set(CATEGORY_HINTS) == set(Category)
