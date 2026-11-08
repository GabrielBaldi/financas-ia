from collections.abc import Sequence
from dataclasses import dataclass

from financas.categories import Category
from financas.text import contains_phrase, normalize


@dataclass(frozen=True, slots=True)
class UserRule:
    pattern: str  # normalized, matched as whole words
    category: Category


def match_user_rules(normalized_description: str, rules: Sequence[UserRule]) -> Category | None:
    """When several of the user's rules match, the longest (most specific) pattern wins."""
    matching = [rule for rule in rules if contains_phrase(normalized_description, rule.pattern)]
    if not matching:
        return None
    return max(matching, key=lambda rule: len(rule.pattern)).category


# Statement boilerplate that says how the money moved, not where it went. Longest first.
_BOILERPLATE = (
    "compra no debito via nupay",
    "compra no debito",
    "compra no credito",
    "transferencia enviada pelo pix",
    "transferencia recebida pelo pix",
    "pagamento de boleto efetuado",
    "pix enviado",
    "pix recebido",
    "pagamento",
    "compra",
    "pag",
    "pg",
)
_PATTERN_WORDS = 3


def suggest_pattern(description: str) -> str:
    """Guess the words that name the merchant, as the starting point for a new rule.

    'Compra no débito - PADARIA PAO QUENTE LTDA 0423' -> 'padaria pao quente'
    """
    text = normalize(description)
    for boilerplate in _BOILERPLATE:
        if text.startswith(boilerplate + " "):
            text = text.removeprefix(boilerplate + " ")
            break
    words = [word for word in text.split() if not any(char.isdigit() for char in word)]
    return " ".join(words[:_PATTERN_WORDS]) or text
