"""The categorization pipeline: user rules -> built-in keywords -> AI -> "A revisar".

Each layer only sees what the previous ones could not decide, so the AI (the only layer that
costs money) is called once per batch of leftovers and never for what a rule already knows.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import batched

from financas.categories import Category, Source
from financas.categorization.ai import AIItem, AISuggestion, TokenUsage, TransactionClassifier
from financas.categorization.keywords import match_keywords
from financas.categorization.user_rules import UserRule, match_user_rules
from financas.text import normalize


@dataclass(frozen=True, slots=True)
class TransactionText:
    description: str
    amount_cents: int
    # False when an answer is already known elsewhere (e.g. a Telegram entry for the same
    # purchase): only the free rule layers run, and what they cannot decide goes to review.
    ask_ai: bool = True


@dataclass(frozen=True, slots=True)
class Decision:
    category: Category | None
    source: Source
    confidence: float | None = None
    suggestion: Category | None = None  # the AI's guess when it was not confident enough


TO_REVIEW = Decision(None, Source.REVIEW)


@dataclass(frozen=True, slots=True)
class CategorizationResult:
    decisions: list[Decision]
    usage: TokenUsage


class Categorizer:
    def __init__(
        self,
        classifier: TransactionClassifier | None,
        min_confidence: float = 0.7,
        batch_size: int = 100,
    ) -> None:
        self._classifier = classifier
        self._min_confidence = min_confidence
        self._batch_size = batch_size

    @property
    def ai_enabled(self) -> bool:
        return self._classifier is not None

    def categorize(
        self, items: Sequence[TransactionText], user_rules: Sequence[UserRule]
    ) -> CategorizationResult:
        decisions: list[Decision | None] = [
            self._decide_by_rules(item, user_rules) for item in items
        ]
        leftovers = [
            index
            for index, decision in enumerate(decisions)
            if decision is None and items[index].ask_ai
        ]

        usage = TokenUsage()
        if self._classifier is not None and leftovers:
            for chunk in batched(leftovers, self._batch_size, strict=False):
                ai_items = [AIItem(i, items[i].description, items[i].amount_cents) for i in chunk]
                result = self._classifier.classify(ai_items)
                usage += result.usage
                for index in chunk:
                    decisions[index] = self._from_suggestion(result.suggestions.get(index))

        return CategorizationResult([decision or TO_REVIEW for decision in decisions], usage)

    @staticmethod
    def _decide_by_rules(item: TransactionText, user_rules: Sequence[UserRule]) -> Decision | None:
        text = normalize(item.description)
        if category := match_user_rules(text, user_rules):
            return Decision(category, Source.USER_RULE)
        if category := match_keywords(text, item.amount_cents):
            return Decision(category, Source.KEYWORD)
        return None

    def _from_suggestion(self, suggestion: AISuggestion | None) -> Decision:
        if suggestion is None:
            return TO_REVIEW
        if suggestion.confidence < self._min_confidence:
            return Decision(None, Source.REVIEW, suggestion.confidence, suggestion.category)
        return Decision(suggestion.category, Source.AI, suggestion.confidence)
