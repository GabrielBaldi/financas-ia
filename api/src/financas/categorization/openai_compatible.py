"""The AI layer over an OpenAI-compatible chat completions API, such as NVIDIA's hosted one.

Same prompt, schema and item-by-item validation as Claude (ai.py), sent with plain httpx2
instead of a second SDK. Any failure (timeout, network, an HTTP error, an empty or invalid
answer) sends the whole batch to "A revisar": an import or a Telegram entry never fails
because of the AI. Logs name the provider, the model and the HTTP status, never the key,
the descriptions or the amounts.
"""

import logging
from collections.abc import Sequence

import httpx2
from pydantic import BaseModel, ValidationError

from financas.categorization.ai import (
    RESPONSE_SCHEMA,
    SYSTEM_PROMPT,
    AIBatchResult,
    AIItem,
    TokenUsage,
    build_user_message,
    parse_suggestions,
)

logger = logging.getLogger(__name__)


# Only the fields the classifier reads. Reasoning models may also send
# `message.reasoning_content`; it is ignored, the answer is in `content`.
class _Message(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    message: _Message
    finish_reason: str | None = None


class _Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class _ChatCompletion(BaseModel):
    choices: list[_Choice]
    usage: _Usage | None = None


# "length": the answer was cut; "content_filter": the provider withheld it. Other values vary
# between OpenAI-compatible servers, so the answer itself is validated instead.
_INCOMPLETE = frozenset({"length", "content_filter"})


class _UnusableAnswerError(Exception):
    """There is no answer to read; `usage` holds the tokens spent anyway."""

    def __init__(self, problem: str, usage: TokenUsage | None = None) -> None:
        super().__init__(problem)
        self.problem = problem
        self.usage = usage or TokenUsage()


class OpenAICompatibleClassifier:
    # ~100 short results fit with room to spare.
    _MAX_TOKENS = 4096

    def __init__(self, http: httpx2.Client, model: str, provider: str) -> None:
        """`http` carries the base URL, the Authorization header and the timeout."""
        self._http = http
        self._model = model
        self._provider = provider

    def __repr__(self) -> str:  # the client holds the key; show only what is safe
        return f"OpenAICompatibleClassifier(provider={self._provider!r}, model={self._model!r})"

    def classify(self, items: Sequence[AIItem]) -> AIBatchResult:
        try:
            text, usage = self._answer(items)
        except _UnusableAnswerError as failure:
            logger.warning(
                "%s (model %r): %s; %d items go to review",
                self._provider,
                self._model,
                failure.problem,
                len(items),
            )
            return AIBatchResult({}, failure.usage)
        return AIBatchResult(parse_suggestions(text, {item.id for item in items}), usage)

    def _answer(self, items: Sequence[AIItem]) -> tuple[str, TokenUsage]:
        """The answer's text and the tokens spent on it."""
        try:
            response = self._http.post("chat/completions", json=self._request_body(items))
        except httpx2.TimeoutException as error:
            raise _UnusableAnswerError("no answer in time") from error
        except httpx2.RequestError as error:
            raise _UnusableAnswerError(f"request failed ({type(error).__name__})") from error

        if response.status_code == httpx2.codes.NOT_FOUND:
            raise _UnusableAnswerError("HTTP 404, is the model available to this key?")
        if response.status_code != httpx2.codes.OK:
            raise _UnusableAnswerError(f"HTTP {response.status_code}")
        try:
            completion = _ChatCompletion.model_validate_json(response.content)
        except ValidationError as error:
            raise _UnusableAnswerError("the response is not a chat completion") from error

        usage = (
            TokenUsage(completion.usage.prompt_tokens, completion.usage.completion_tokens)
            if completion.usage
            else TokenUsage()
        )
        choice = completion.choices[0] if completion.choices else None
        if choice is not None and choice.finish_reason in _INCOMPLETE:
            raise _UnusableAnswerError(f"stopped with {choice.finish_reason!r}", usage)
        text = choice.message.content if choice is not None else None
        if text is None or not text.strip():
            # Seen with reasoning models that spend the whole answer on thinking.
            raise _UnusableAnswerError("empty answer", usage)
        return text, usage

    def _request_body(self, items: Sequence[AIItem]) -> dict[str, object]:
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_message(items)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "categorias", "schema": RESPONSE_SCHEMA, "strict": True},
            },
            "temperature": 0,
            "max_tokens": self._MAX_TOKENS,
        }


def make_openai_compatible_classifier(
    *,
    provider: str,
    api_key: str,
    model: str,
    base_url: str,
    timeout: float = 60.0,
    transport: httpx2.BaseTransport | None = None,
) -> OpenAICompatibleClassifier:
    """Tests pass a fake server as `transport`; no request is made here."""
    http = httpx2.Client(
        base_url=base_url.rstrip("/") + "/",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=httpx2.Timeout(timeout),
        transport=transport,
    )
    return OpenAICompatibleClassifier(http, model, provider)
