import re
import unicodedata

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """Lowercase, drop accents and collapse everything that is not a letter or digit into one space.

    'Compra no débito - PADARIA São João*' -> 'compra no debito padaria sao joao'
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _NON_ALPHANUMERIC.sub(" ", without_accents.lower()).strip()


def contains_phrase(normalized_text: str, normalized_phrase: str) -> bool:
    """Whole-word match: 'uber' matches 'uber trip' but not 'uberlandia'."""
    return f" {normalized_phrase} " in f" {normalized_text} "
