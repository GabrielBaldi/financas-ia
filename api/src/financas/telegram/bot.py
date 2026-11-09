"""What the bot does with each message: link the chat, run a command or log an entry.

Only private chats are served. A chat that is not linked to a user can do one thing, send
/conectar with a code from the web app; everything else gets a short "this bot is private".
Logs never contain message text, amounts or chat ids.
"""

import datetime as dt
import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from financas.categorization.pipeline import Categorizer
from financas.localtime import local_today
from financas.models import Account, User, utc_now
from financas.services.accounts import accounts_starting_with, get_account, list_accounts
from financas.services.manual_entries import (
    ManualEntry,
    add_manual_entry,
    recent_entries,
    undo_last_entry,
)
from financas.services.telegram_link import (
    PairingResult,
    chat_is_locked,
    redeem_pairing_code,
    set_default_account,
    unlink_telegram,
    user_for_chat,
)
from financas.telegram import replies
from financas.telegram.parser import EntryParseError, parse_entry

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    chat_id: int
    chat_type: str  # "private", "group", "supergroup" or "channel"
    text: str | None  # None for photos, stickers, voice...
    from_bot: bool = False


def split_command(text: str) -> tuple[str | None, str]:
    """'/conta  Nubank' -> ('/conta', 'Nubank'); '/ajuda@MeuBot' -> ('/ajuda', '')."""
    if not text.startswith("/"):
        return None, text
    head, *rest = text.split(maxsplit=1)
    return head.split("@", 1)[0].lower(), rest[0].strip() if rest else ""


class TelegramBot:
    """Turns one message into at most one reply.

    Synchronous on purpose: it uses the database (and maybe Claude), so the polling loop runs
    it in a worker thread. `clock` is injectable so tests control expiry and lockouts.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        categorizer: Categorizer,
        clock: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._categorizer = categorizer
        self._clock = clock or utc_now

    def handle(self, message: IncomingMessage) -> str | None:
        if message.chat_type != "private" or message.from_bot:
            return None
        now = self._clock()
        command, argument = split_command(message.text or "")
        with self._session_factory() as session:
            if command == "/conectar":
                return self._connect(session, message.chat_id, argument, now)
            user = user_for_chat(session, message.chat_id)
            if user is None:
                return self._stranger(session, message.chat_id, now)
            if command is not None:
                return self._command(session, user, command, argument)
            if message.text is None:
                return replies.TEXT_ONLY
            return self._log_entry(session, user, message.text, now)

    @staticmethod
    def _stranger(session: Session, chat_id: int, now: dt.datetime) -> str | None:
        """A chat nobody linked: explain how to connect, unless it is locked for guessing."""
        if chat_is_locked(session, chat_id, now):
            return None
        logger.info("Mensagem de um chat não conectado")
        return replies.NOT_LINKED

    def _connect(self, session: Session, chat_id: int, code: str, now: dt.datetime) -> str | None:
        if chat_is_locked(session, chat_id, now):
            return None
        if not code:
            return replies.CONNECT_USAGE
        pairing = redeem_pairing_code(session, chat_id, code, now)
        if pairing.result is PairingResult.LOCKED_OUT:
            logger.warning("Código errado pela 5ª vez: chat ignorado por 15 minutos")
            return replies.LOCKED_OUT
        if pairing.user is None:
            logger.info("Código de conexão errado")
            return replies.WRONG_CODE
        logger.info("Chat conectado ao usuário %d", pairing.user.id)
        return replies.linked(self._default_account(session, pairing.user))

    def _command(self, session: Session, user: User, command: str, argument: str) -> str:
        match command:
            case "/start" | "/ajuda" | "/help":
                return replies.HELP
            case "/desconectar":
                unlink_telegram(session, user)
                logger.info("Usuário %d desconectou o chat", user.id)
                return replies.UNLINKED
            case "/desfazer":
                entry = undo_last_entry(session, user.id)
                return replies.undone(entry) if entry else replies.NOTHING_TO_UNDO
            case "/ultimos":
                return replies.recent(recent_entries(session, user.id))
            case "/conta":
                return self._account_command(session, user, argument)
            case _:
                return replies.UNKNOWN_COMMAND

    def _account_command(self, session: Session, user: User, query: str) -> str:
        if not query:
            return replies.default_account(
                self._default_account(session, user), list_accounts(session, user.id)
            )
        matches = accounts_starting_with(session, user.id, query)
        if len(matches) != 1:
            return self._account_problem(session, user, query, matches)
        set_default_account(session, user, matches[0])
        return replies.default_account_set(matches[0])

    def _log_entry(self, session: Session, user: User, text: str, now: dt.datetime) -> str:
        try:
            parsed = parse_entry(text, local_today(now))
        except EntryParseError as error:
            return str(error)

        account = None
        if parsed.account_hint is not None:
            matches = accounts_starting_with(session, user.id, parsed.account_hint)
            if len(matches) != 1:
                return self._account_problem(session, user, parsed.account_hint, matches)
            account = matches[0]

        outcome = add_manual_entry(
            session,
            user=user,
            entry=ManualEntry(parsed.amount_cents, parsed.description, parsed.date),
            categorizer=self._categorizer,
            account=account,
        )
        logger.info(
            "Lançamento do usuário %d %s",
            user.id,
            "anotado numa linha do extrato" if outcome.already_in_statement else "salvo",
        )
        return replies.entry_saved(outcome)

    @staticmethod
    def _default_account(session: Session, user: User) -> Account | None:
        if user.telegram_default_account_id is None:
            return None
        return get_account(session, user.id, user.telegram_default_account_id)

    @staticmethod
    def _account_problem(session: Session, user: User, query: str, matches: list[Account]) -> str:
        if matches:
            return replies.account_ambiguous(query, matches)
        return replies.account_not_found(query, list_accounts(session, user.id))
