"""Run the Telegram bot: `uv run python -m financas.telegram_bot`.

Needs TELEGRAM_BOT_TOKEN (from @BotFather) and the same DATABASE_URL as the API; with an
AI key set (ANTHROPIC_API_KEY or NVIDIA_API_KEY), entries the rules do not know go to the AI,
as in an import. Long polling means the computer only makes outbound HTTPS requests: no open port,
no public address. Stop it with Ctrl+C.
"""

import asyncio
import logging
import sys

import httpx2
from sqlalchemy.orm import Session, sessionmaker

from financas.categorization.factory import make_categorizer
from financas.config import Settings, get_settings
from financas.db import make_engine, make_session_factory
from financas.telegram.bot import TelegramBot
from financas.telegram.client import TelegramClient, TelegramError
from financas.telegram.polling import poll

logger = logging.getLogger("financas.telegram")

EXIT_NO_TOKEN = 2
EXIT_TELEGRAM_REFUSED = 1

_HINTS = {
    401: "o Telegram recusou o token. Confira TELEGRAM_BOT_TOKEN (o @BotFather mostra de novo).",
    404: "o Telegram não reconheceu o token. Confira TELEGRAM_BOT_TOKEN.",
    409: "outro processo já está lendo as mensagens deste bot (ou há um webhook configurado).",
}


def silence_http_logs() -> None:
    """httpx2 logs every request URL at INFO, and a Bot API URL contains the token."""
    for name in ("httpx2", "httpcore2", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


async def run(
    token: str,
    settings: Settings,
    session_factory: sessionmaker[Session],
    *,
    transport: httpx2.AsyncBaseTransport | None = None,
    stop: asyncio.Event | None = None,
) -> None:
    """Start the bot. Tests pass a fake Telegram as `transport` and a `stop` event."""
    silence_http_logs()
    bot = TelegramBot(session_factory, make_categorizer(settings))
    async with httpx2.AsyncClient(transport=transport) as http:
        client = TelegramClient(token, http, api_url=settings.telegram_api_url)
        me = await client.get_me()
        logger.info("Bot @%s no ar, esperando mensagens. Ctrl+C para parar.", me.username)
        await poll(client, bot.handle, stop=stop)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    if settings.telegram_bot_token is None:
        print(
            "Defina TELEGRAM_BOT_TOKEN em api/.env (README, seção Lançar gastos pelo Telegram).",
            file=sys.stderr,
        )
        return EXIT_NO_TOKEN

    engine = make_engine(settings.database_url)
    try:
        token = settings.telegram_bot_token.get_secret_value()
        asyncio.run(run(token, settings, make_session_factory(engine)))
    except KeyboardInterrupt:
        logger.info("Bot parado.")
    except TelegramError as error:
        logger.error("Parando: %s", _HINTS.get(error.status, str(error)))
        return EXIT_TELEGRAM_REFUSED
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
