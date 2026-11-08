from financas.categories import Category, Source
from financas.categorization.pipeline import Categorizer, Decision, TransactionText
from financas.categorization.user_rules import UserRule
from tests.helpers import FakeClassifier

ITEMS = [
    TransactionText("Compra no débito - Padaria Pão Quente", -1200),  # keyword
    TransactionText("EC *CANTINADOPORTO", -8800),  # user rule
    TransactionText("SUMUP *RECANTO VERDE", -6400),  # AI, confident
    TransactionText("PAG*JOSEEXEMPLO", -4500),  # AI, unsure
    TransactionText("MP *LOJADOZE", -3990),  # AI has no answer
]
USER_RULES = [UserRule("cantinadoporto", Category.LAZER)]


def test_each_layer_only_sees_what_the_previous_ones_left() -> None:
    ai = FakeClassifier(
        {
            "SUMUP *RECANTO VERDE": (Category.ALIMENTACAO, 0.91),
            "PAG*JOSEEXEMPLO": (Category.SAUDE, 0.45),
        }
    )

    result = Categorizer(ai, min_confidence=0.7).categorize(ITEMS, USER_RULES)

    assert result.decisions == [
        Decision(Category.ALIMENTACAO, Source.KEYWORD),
        Decision(Category.LAZER, Source.USER_RULE),
        Decision(Category.ALIMENTACAO, Source.AI, confidence=0.91),
        Decision(None, Source.REVIEW, confidence=0.45, suggestion=Category.SAUDE),
        Decision(None, Source.REVIEW),
    ]
    # One request with only the three leftovers.
    assert [[item.description for item in batch] for batch in ai.batches] == [
        ["SUMUP *RECANTO VERDE", "PAG*JOSEEXEMPLO", "MP *LOJADOZE"]
    ]
    assert result.usage.input_tokens == 300


def test_user_rules_beat_keyword_rules() -> None:
    rules = [UserRule("padaria pao quente", Category.LAZER)]

    result = Categorizer(None).categorize(ITEMS[:1], rules)

    assert result.decisions == [Decision(Category.LAZER, Source.USER_RULE)]


def test_without_ai_leftovers_go_to_review_and_nothing_is_spent() -> None:
    result = Categorizer(None).categorize(ITEMS, USER_RULES)

    assert [d.source for d in result.decisions[2:]] == [Source.REVIEW] * 3
    assert result.usage.input_tokens == 0


def test_ai_is_not_called_when_rules_cover_everything() -> None:
    ai = FakeClassifier()

    Categorizer(ai).categorize(ITEMS[:2], USER_RULES)

    assert ai.batches == []


def test_large_imports_are_split_into_batches() -> None:
    ai = FakeClassifier()
    items = [TransactionText(f"LOJA DESCONHECIDA {n}", -100) for n in range(5)]

    Categorizer(ai, batch_size=2).categorize(items, [])

    assert [len(batch) for batch in ai.batches] == [2, 2, 1]
