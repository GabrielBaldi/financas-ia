"""Everything the bot says, in pt-BR. Plain text: no Markdown, so user text needs no escaping."""

import datetime as dt
from collections.abc import Sequence

from financas.categories import CATEGORY_LABELS, Source
from financas.models import Account, Origin, Transaction
from financas.services.accounts import MANUAL_ACCOUNT_NAME
from financas.services.manual_entries import EntryOutcome
from financas.telegram.parser import EXAMPLES

SOURCE_LABELS: dict[Source, str] = {
    Source.USER_RULE: "sua regra",
    Source.KEYWORD: "regra padrão",
    Source.AI: "IA",
    Source.MANUAL: "você",
    Source.REVIEW: "a revisar",
}

NOT_LINKED = (
    "Este bot é privado: ele só anota gastos de quem conectou a própria conta.\n\n"
    "Para conectar, abra o Finanças com IA, entre na página Telegram, toque em "
    "“Gerar código” e envie aqui:\n/conectar CÓDIGO"
)
CONNECT_USAGE = (
    "Envie /conectar seguido do código de 6 dígitos que aparece no app (página Telegram)."
)
WRONG_CODE = "Código inválido ou expirado. Gere um novo no app e tente de novo."
LOCKED_OUT = "Muitos códigos errados. Este chat vai ser ignorado pelos próximos 15 minutos."
UNLINKED = "Chat desconectado. Para voltar, gere um novo código no app."
TEXT_ONLY = f"Por enquanto eu só entendo texto. Exemplos: {EXAMPLES}"
UNKNOWN_COMMAND = "Não conheço esse comando. Veja /ajuda."
NOTHING_TO_UNDO = "Nada para desfazer: não há lançamento seu esperando o extrato."
NO_ENTRIES = "Você ainda não lançou nada pelo Telegram."
SOMETHING_WENT_WRONG = "Algo deu errado do meu lado. Tente de novo em instantes."

HELP = """Mande um gasto por mensagem, em qualquer ordem:
32,90 almoço
uber 23 ontem
R$ 1.234,56 aluguel 05/11
mercado 150 #nubank (vai para a conta com "nubank" no nome)

Entradas: +50 pix recebido, ou recebi 50 salário.
Datas: hoje, ontem, anteontem, 05/11 ou 05/11/2026.

/ultimos - os últimos 5 lançamentos
/desfazer - apaga o último lançamento
/conta - mostra ou troca a conta padrão (/conta nubank)
/desconectar - desliga este chat"""


MINUS = "\u2212"  # a real minus sign, as in the web app


def money(cents: int) -> str:
    """-123456 -> 'R$ 1.234,56' after a real minus sign (as in the web app), 5000 -> '+R$ 50,00'."""
    sign = "+" if cents > 0 else MINUS if cents < 0 else ""
    reais, centavos = divmod(abs(cents), 100)
    return f"{sign}R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def day(date: dt.date) -> str:
    return date.strftime("%d/%m/%Y")


def category_line(transaction: Transaction) -> str:
    if transaction.category is None:
        return "Categoria: a revisar (escolha no app)"
    decided_by = SOURCE_LABELS[transaction.categorized_by]
    if transaction.categorized_by is Source.AI and transaction.confidence is not None:
        decided_by += f", {round(transaction.confidence * 100)}%"
    return f"Categoria: {CATEGORY_LABELS[transaction.category]} ({decided_by})"


def linked(default_account: Account | None) -> str:
    account = default_account.name if default_account else MANUAL_ACCOUNT_NAME
    return (
        "Pronto, este chat está conectado.\n"
        f"Mande um gasto assim: 32,90 almoço. Ele vai para a conta {account}.\n"
        "Veja tudo o que dá para fazer em /ajuda."
    )


def entry_saved(outcome: EntryOutcome) -> str:
    row = outcome.transaction
    if outcome.already_in_statement:
        return (
            f"Esse já estava no extrato: {money(row.amount_cents)} em {day(row.date)} "
            f"({outcome.account.name}).\n"
            f"Anotei “{row.note}” nele.\n"
            f"{category_line(row)}"
        )
    return (
        f"Anotado: {money(row.amount_cents)} · {row.description}\n"
        f"{category_line(row)}\n"
        f"Conta: {outcome.account.name} · {day(row.date)}\n"
        "Errou? /desfazer"
    )


def undone(entry: Transaction) -> str:
    return f"Apagado: {money(entry.amount_cents)} · {entry.description} ({day(entry.date)})."


def recent(entries: Sequence[Transaction]) -> str:
    if not entries:
        return NO_ENTRIES
    lines = ["Últimos lançamentos:"]
    for entry in entries:
        text = entry.note or entry.description  # merged rows keep the user's words as the note
        category = CATEGORY_LABELS[entry.category] if entry.category else "a revisar"
        merged = " · conferido no extrato" if entry.origin is Origin.IMPORT else ""
        lines.append(
            f"{entry.date:%d/%m} · {money(entry.amount_cents)} · {text} · {category}{merged}"
        )
    return "\n".join(lines)


def account_list(accounts: Sequence[Account]) -> str:
    return ", ".join(account.name for account in accounts) or "nenhuma ainda"


def default_account(current: Account | None, accounts: Sequence[Account]) -> str:
    head = (
        f"Conta padrão: {current.name}."
        if current
        else f"Sem conta padrão: os lançamentos vão para “{MANUAL_ACCOUNT_NAME}”."
    )
    return (
        f"{head}\nSuas contas: {account_list(accounts)}.\n"
        "Para trocar: /conta e parte do nome (ex.: /conta nubank)."
    )


def default_account_set(account: Account) -> str:
    return f"Conta padrão agora é {account.name}."


def account_not_found(query: str, accounts: Sequence[Account]) -> str:
    return f"Nenhuma conta com “{query}” no nome. Suas contas: {account_list(accounts)}."


def account_ambiguous(query: str, matches: Sequence[Account]) -> str:
    return (
        f"Mais de uma conta com “{query}” no nome: {account_list(matches)}. Seja mais específico."
    )
