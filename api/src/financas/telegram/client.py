"""A small client for the three Telegram Bot API methods the bot needs, over httpx2.

Network errors, 5xx and 429 are retried with exponential backoff; a 429 waits as long as
Telegram's `retry_after` asks. Anything else (a bad token, a malformed request) is raised as
TelegramError, since retrying cannot fix it. The token is part of every URL, so URLs,
request bodies and exception messages are never logged.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx2
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

TEXT_LIMIT = 4096  # Telegram refuses longer messages


class TelegramError(Exception):
    """Telegram refused the request and retrying will not help."""

    def __init__(self, status: int, description: str) -> None:
        super().__init__(f"HTTP {status}: {description}")
        self.status = status
        self.description = description


class TelegramUnavailableError(Exception):
    """Telegram could not be reached within the allowed attempts."""


@dataclass(frozen=True, slots=True)
class Backoff:
    first: float = 1.0
    maximum: float = 60.0

    def delays(self) -> Iterator[float]:
        """1, 2, 4, ... seconds, capped at `maximum`."""
        delay = self.first
        while True:
            yield delay
            delay = min(delay * 2, self.maximum)


# Only the fields the bot reads; Telegram sends many more, which are ignored.
class Chat(BaseModel):
    id: int
    type: str


class Sender(BaseModel):
    is_bot: bool = False


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    chat: Chat
    text: str | None = None
    sender: Sender | None = Field(default=None, alias="from")


class Update(BaseModel):
    update_id: int
    message: Message | None = None


class BotInfo(BaseModel):
    username: str


class _ResponseParameters(BaseModel):
    retry_after: float | None = None


class _Response(BaseModel):
    ok: bool
    result: Any = None
    error_code: int | None = None
    description: str | None = None
    parameters: _ResponseParameters | None = None


Sleep = Callable[[float], Awaitable[None]]


class TelegramClient:
    def __init__(
        self,
        token: str,
        http: httpx2.AsyncClient,
        *,
        api_url: str = "https://api.telegram.org",
        backoff: Backoff | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._base = f"{api_url.rstrip('/')}/bot{token}"
        self._http = http
        self._backoff = backoff or Backoff()
        self._sleep = sleep

    def __repr__(self) -> str:  # never show the token
        return "TelegramClient()"

    async def get_me(self) -> BotInfo:
        """Checks the token at start-up (a wrong one raises TelegramError 401). Like
        get_updates, it waits for the network for as long as it takes."""
        result = await self._call("getMe", {}, read_timeout=15, attempts=None)
        return BotInfo.model_validate(result)

    async def get_updates(self, offset: int | None, timeout: int) -> list[Update]:
        """Long polling: waits up to `timeout` seconds for messages. Retries for as long as
        it takes (the network may be down for hours), so it only returns or raises
        TelegramError. Calling it with `offset` confirms every update before that id."""
        payload: dict[str, object] = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        result = await self._call("getUpdates", payload, read_timeout=timeout + 10, attempts=None)
        return _parse_updates(result)

    async def confirm(self, offset: int) -> None:
        """Confirm updates before `offset` without waiting for new ones (used at shutdown)."""
        payload = {"offset": offset, "timeout": 0, "limit": 1, "allowed_updates": ["message"]}
        await self._call("getUpdates", payload, read_timeout=10, attempts=1)

    async def send_message(self, chat_id: int, text: str) -> None:
        """Plain text, no Markdown: the user's own words need no escaping."""
        payload = {"chat_id": chat_id, "text": text[:TEXT_LIMIT]}
        await self._call("sendMessage", payload, read_timeout=15, attempts=4)

    async def _call(
        self, method: str, payload: dict[str, object], *, read_timeout: float, attempts: int | None
    ) -> Any:
        """POST a method; `attempts=None` retries forever."""
        timeout = httpx2.Timeout(10.0, read=read_timeout)
        delays = self._backoff.delays()
        attempt = 0
        while True:
            attempt += 1
            wait = next(delays)
            try:
                response = await self._http.post(
                    f"{self._base}/{method}", json=payload, timeout=timeout
                )
            except httpx2.TransportError as error:
                problem = f"falha de rede ({type(error).__name__})"
            else:
                body = _read_body(response)
                if response.status_code == 200 and body.ok:
                    return body.result
                if response.status_code == 429:
                    retry_after = body.parameters.retry_after if body.parameters else None
                    wait = retry_after if retry_after is not None else wait
                    problem = "limite de mensagens do Telegram (429)"
                elif response.status_code >= 500:
                    problem = f"Telegram fora do ar (HTTP {response.status_code})"
                else:
                    raise TelegramError(response.status_code, body.description or "sem detalhes")

            if attempts is not None and attempt >= attempts:
                raise TelegramUnavailableError(f"{method}: {problem}")
            logger.warning("%s: %s; nova tentativa em %.0f s", method, problem, wait)
            await self._sleep(wait)


def _read_body(response: httpx2.Response) -> _Response:
    try:
        return _Response.model_validate_json(response.content)
    except ValidationError:
        return _Response(ok=False, description="resposta que não é JSON")


def _parse_updates(result: object) -> list[Update]:
    """Updates the bot cannot read still count, so the offset moves past them."""
    updates = []
    for raw in result if isinstance(result, list) else []:
        try:
            updates.append(Update.model_validate(raw))
        except ValidationError:
            update_id = raw.get("update_id") if isinstance(raw, dict) else None
            if isinstance(update_id, int):
                updates.append(Update(update_id=update_id))
    return updates
