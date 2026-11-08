import pytest

from financas.categories import Category
from financas.categorization.keywords import KEYWORD_RULES, match_keywords
from financas.categorization.user_rules import UserRule, match_user_rules, suggest_pattern
from financas.text import contains_phrase, normalize


def test_normalize_strips_accents_case_and_punctuation() -> None:
    assert normalize("Compra no débito - PADARIA São João*") == "compra no debito padaria sao joao"


def test_contains_phrase_matches_whole_words_only() -> None:
    assert contains_phrase("uber trip", "uber")
    assert not contains_phrase("uberlandia centro", "uber")
    assert contains_phrase("compra no debito via nupay ifood", "nupay ifood")


def test_every_keyword_is_already_normalized() -> None:
    for rule in KEYWORD_RULES:
        for keyword in rule.keywords:
            assert normalize(keyword) == keyword, keyword


@pytest.mark.parametrize(
    ("description", "amount", "expected"),
    [
        ("UBER *TRIP HELP.UBER.COM", -2345, Category.TRANSPORTE),
        ("UBER EATS *PEDIDO", -4590, Category.ALIMENTACAO),  # specific before generic
        ("Amazon Prime Canais", -1490, Category.ASSINATURAS),
        ("AMAZON MARKETPLACE", -8990, Category.COMPRAS),
        ("MERCADOLIVRE*3PRODUTOS", -18990, Category.COMPRAS),  # not "mercado"
        ("Supermercado Bom Preço", -31280, Category.MERCADO),
        ("Transferência enviada pelo Pix - Ana", -25000, Category.TRANSFERENCIAS),
        ("Transferência recebida pelo Pix - Ana", 25000, Category.RECEITAS),
        ("Compra no débito via NuPay - iFood", -5000, Category.ALIMENTACAO),  # merchant beats Pix
        ("Pagamento de fatura", -125000, Category.FATURA),
        ("IOF compra internacional", -320, Category.TAXAS),
    ],
)
def test_keyword_rules(description: str, amount: int, expected: Category) -> None:
    assert match_keywords(normalize(description), amount) == expected


def test_unknown_merchant_matches_no_keyword() -> None:
    assert match_keywords(normalize("EC *CANTINADOPORTO"), -8800) is None


def test_user_rules_prefer_the_longest_matching_pattern() -> None:
    rules = [
        UserRule("posto", Category.TRANSPORTE),
        UserRule("posto do ze conveniencia", Category.ALIMENTACAO),
    ]

    assert match_user_rules("posto do ze conveniencia", rules) is Category.ALIMENTACAO
    assert match_user_rules("posto shell", rules) is Category.TRANSPORTE
    assert match_user_rules("padaria", rules) is None


@pytest.mark.parametrize(
    ("description", "pattern"),
    [
        ("Compra no débito - PADARIA PAO QUENTE LTDA 0423", "padaria pao quente"),
        ("PAG*JoseExemplo", "joseexemplo"),
        ("Transferência enviada pelo Pix - Ana Exemplo", "ana exemplo"),
        ("EC *CANTINADOPORTO", "ec cantinadoporto"),
        ("99APP 1234", "99app 1234"),  # nothing but digits left: keep the whole text
    ],
)
def test_suggest_pattern_keeps_the_merchant_words(description: str, pattern: str) -> None:
    assert suggest_pattern(description) == pattern
