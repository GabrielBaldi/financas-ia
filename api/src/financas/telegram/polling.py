"""The long-polling loop: ask Telegram for new messages, answer each, repeat.

Telegram keeps an update until a getUpdates call asks for a later offset, so the offset moves
past each update before it is handled: a message that crashes the handler is not delivered
again forever. On shutdown the loop confirms what it already handled, so restarting the bot
does not log the same expense twice.
"""

import asyncio
import logging
from collections.abc import Callable

from financas.telegram import replies
from financas.telegram.bot import IncomingMessage
from financas.telegram.client import TelegramClient, TelegramError, TelegramUnavailableError, Update

logger = logging.getLogger(__name__)

POLL_TIMEOUT = 30  # seconds Telegram holds a getUpdates call open while there is nothing new

Handler = Callable[[IncomingMessage], str | None]


def incoming(update: Update) -> IncomingMessage | None:
    message = update.message
    if message is None:
        return None
    return IncomingMessage(
        chat_id=message.chat.id,
        chat_type=message.chat.type,
        text=message.text,
        from_bot=message.sender is not None and message.sender.is_bot,
    )


async def answer(client: TelegramClient, handle: Handler, update: Update) -> None:
    message = incoming(update)
    if message is None:
        return
    try:
        # The handler talks to the database (and maybe Claude): keep it off the event loop.
        reply = await asyncio.to_thread(handle, message)
    except Exception as error:
        # Only the type: SQL errors quote their parameters, which would leak the message.
        logger.error("Erro ao tratar uma mensagem (%s); ela foi descartada", type(error).__name__)
        reply = replies.SOMETHING_WENT_WRONG
    if reply is None:
        return
    try:
        await client.send_message(message.chat_id, reply)
    except (TelegramError, TelegramUnavailableError) as error:
        logger.warning("Não foi possível responder (%s)", type(error).__name__)


async def poll(
    client: TelegramClient,
    handle: Handler,
    *,
    timeout: int = POLL_TIMEOUT,
    stop: asyncio.Event | None = None,
) -> None:
    """Runs until cancelled (Ctrl+C) or until `stop` is set (tests)."""
    offset: int | None = None
    confirmed = offset
    try:
        while stop is None or not stop.is_set():
            updates = await client.get_updates(offset, timeout)
            confirmed = offset  # that call confirmed every update before `offset`
            for update in updates:
                offset = update.update_id + 1
                await answer(client, handle, update)
    finally:
        if offset is not None and offset != confirmed:
            try:
                await client.confirm(offset)
            except (TelegramError, TelegramUnavailableError) as error:
                logger.warning(
                    "Não foi possível confirmar as últimas mensagens (%s)", type(error).__name__
                )
