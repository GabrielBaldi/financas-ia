"""OpenAICompatibleClassifier against a fake NVIDIA endpoint (httpx2.MockTransport).

No request leaves the process: the fake records each request and answers from the test.
"""

import json
import logging
from typing import Any

import httpx2
import pytest

from financas.categories import Category
from financas.categorization.ai import (
    RESPONSE_SCHEMA,
    SYSTEM_PROMPT,
    AIItem,
    TokenUsage,
    build_user_message,
)
from financas.categorization.openai_compatible import (
    OpenAICompatibleClassifier,
    make_openai_compatible_classifier,
)

API_KEY = "nvapi-chave-de-teste"
MODEL = "minimaxai/minimax-m3.1-flash"
BASE_URL = "https://integrate.api.nvidia.com/v1"
ITEMS = [AIItem(0, "EC *CANTINADOPORTO", -8800), AIItem(1, "PAG*JOSEEXEMPLO", -4500)]


class FakeNvidia:
    def __init__(self, answer: httpx2.Response | Exception) -> None:
        self.answer = answer
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = json.loads(self.requests[0].content)
        return body


def classifier_for(
    answer: httpx2.Response | Exception, *, base_url: str = BASE_URL, timeout: float = 60.0
) -> tuple[OpenAICompatibleClassifier, FakeNvidia]:
    fake = FakeNvidia(answer)
    classifier = make_openai_compatible_classifier(
        provider="NVIDIA",
        api_key=API_KEY,
        model=MODEL,
        base_url=base_url,
        timeout=timeout,
        transport=httpx2.MockTransport(fake),
    )
    return classifier, fake


def completion(
    content: str | None,
    *,
    finish_reason: str | None = "stop",
    usage: dict[str, int] | None = None,
    **message: object,
) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content, **message},
                    "finish_reason": finish_reason,
                }
            ],
            "usage": usage or {"prompt_tokens": 900, "completion_tokens": 60, "total_tokens": 960},
        },
    )


def results(*items: dict[str, object]) -> str:
    return json.dumps({"results": list(items)})


def test_one_structured_request_for_the_whole_batch() -> None:
    classifier, fake = classifier_for(completion(results()), timeout=45)

    classifier.classify(ITEMS)

    assert len(fake.requests) == 1
    request = fake.requests[0]
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert request.extensions["timeout"]["read"] == 45
    assert fake.body() == {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(ITEMS)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "categorias", "schema": RESPONSE_SCHEMA, "strict": True},
        },
        "temperature": 0,
        "max_tokens": 4096,
    }


def test_a_trailing_slash_in_the_base_url_is_fine() -> None:
    classifier, fake = classifier_for(completion(results()), base_url=f"{BASE_URL}/")

    classifier.classify(ITEMS)

    assert str(fake.requests[0].url) == f"{BASE_URL}/chat/completions"


def test_answers_become_suggestions_and_usage_is_counted() -> None:
    answer = results(
        {"id": 0, "category": "alimentacao", "confidence": 0.92},
        {"id": 1, "category": "transferencias", "confidence": 0.4},
    )
    # Reasoning models also send their thinking; only `content` is read.
    response = completion(answer, reasoning_content="Cantina parece restaurante...")
    classifier, _ = classifier_for(response)

    result = classifier.classify(ITEMS)

    assert result.suggestions[0].category is Category.ALIMENTACAO
    assert result.suggestions[1].confidence == 0.4
    assert result.usage == TokenUsage(900, 60)


def test_invalid_items_are_dropped_one_by_one() -> None:
    answer = results(
        {"id": 0, "category": "lazer", "confidence": 0.9},
        {"id": 1, "category": "categoria-inventada", "confidence": 0.9},
        {"id": 7, "category": "lazer", "confidence": 0.9},  # an id we never sent
        {"id": 1, "category": "lazer", "confidence": 1.7},
    )
    classifier, _ = classifier_for(completion(answer))

    suggestions = classifier.classify(ITEMS).suggestions

    assert list(suggestions) == [0]
    assert suggestions[0].category is Category.LAZER


@pytest.mark.parametrize(
    "response",
    [
        completion("isto não é JSON"),
        completion('{"results": "nada"}'),
        completion(""),
        completion("   \n"),
        completion(None),  # a reasoning model that spent the answer on thinking
        completion('{"results": [{"id": 0, "categ', finish_reason="length"),
        completion(
            results({"id": 0, "category": "lazer", "confidence": 0.9}), finish_reason="length"
        ),
        completion(None, finish_reason="content_filter"),
    ],
)
def test_unusable_answers_send_everything_to_review(response: httpx2.Response) -> None:
    classifier, _ = classifier_for(response)

    result = classifier.classify(ITEMS)

    assert result.suggestions == {}
    assert result.usage == TokenUsage(900, 60)  # the tokens were still spent


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(404, json={"detail": "Function 'abc': Not found for account 'xyz'"}),
        httpx2.Response(401, json={"detail": "Unauthorized"}),
        httpx2.Response(429, json={"detail": "Too many requests"}),
        httpx2.Response(500, text="Internal Server Error"),
        httpx2.Response(200, text="<html>gateway</html>"),
        httpx2.Response(200, json={"choices": []}),
        httpx2.Response(200, json={"error": "sem choices"}),
    ],
)
def test_http_errors_and_odd_bodies_do_not_break_the_import(response: httpx2.Response) -> None:
    classifier, _ = classifier_for(response)

    result = classifier.classify(ITEMS)

    assert result.suggestions == {}
    assert result.usage == TokenUsage()


@pytest.mark.parametrize(
    "error",
    [
        httpx2.ReadTimeout("timed out"),
        httpx2.ConnectTimeout("timed out"),
        httpx2.ConnectError("connection refused"),
        httpx2.RemoteProtocolError("server disconnected"),
    ],
)
def test_timeouts_and_network_errors_do_not_break_the_import(error: Exception) -> None:
    classifier, fake = classifier_for(error)

    result = classifier.classify(ITEMS)

    assert result.suggestions == {}
    assert result.usage == TokenUsage()
    assert len(fake.requests) == 1  # one attempt: a hanging model is not waited on twice


def test_a_missing_usage_block_counts_as_zero_tokens() -> None:
    answer = results({"id": 0, "category": "lazer", "confidence": 0.9})
    response = httpx2.Response(
        200, json={"choices": [{"message": {"content": answer}, "finish_reason": "stop"}]}
    )
    classifier, _ = classifier_for(response)

    result = classifier.classify(ITEMS)

    assert result.suggestions[0].category is Category.LAZER
    assert result.usage == TokenUsage()


@pytest.mark.parametrize(
    "answer",
    [
        httpx2.ReadTimeout("timed out"),
        httpx2.ConnectError("connection refused"),
        httpx2.Response(404, json={"detail": "Function not found for account"}),
        httpx2.Response(200, text="<html>gateway</html>"),
        completion(None),
        completion('{"results": [{"id": 0, "categ', finish_reason="length"),
        completion("isto não é JSON"),
    ],
)
def test_logs_never_show_the_key_or_the_transactions(
    answer: httpx2.Response | Exception, caplog: pytest.LogCaptureFixture
) -> None:
    classifier, _ = classifier_for(answer)

    with caplog.at_level(logging.DEBUG):
        classifier.classify(ITEMS)

    assert "to review" in caplog.text
    for secret in (API_KEY, "CANTINADOPORTO", "JOSEEXEMPLO", "88.00", "45.00"):
        assert secret not in caplog.text
    assert API_KEY not in repr(classifier)


def test_a_404_hints_that_the_model_may_be_unavailable(caplog: pytest.LogCaptureFixture) -> None:
    classifier, _ = classifier_for(httpx2.Response(404, json={"detail": "Not found"}))

    with caplog.at_level(logging.WARNING):
        classifier.classify(ITEMS)

    assert f"NVIDIA (model '{MODEL}'): HTTP 404, is the model available" in caplog.text
