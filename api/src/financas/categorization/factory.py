"""Build the AI layer the settings ask for. The API, the Telegram bot and the evaluation
script all go through here, so the provider is chosen in one place."""

import logging

from financas.categorization.ai import TransactionClassifier, make_claude_classifier
from financas.categorization.openai_compatible import make_openai_compatible_classifier
from financas.categorization.pipeline import Categorizer
from financas.config import AI_PROVIDER_LABELS, Settings
from financas.services.imports import AIPricing

logger = logging.getLogger(__name__)


def make_classifier(settings: Settings) -> TransactionClassifier | None:
    """The chosen provider's classifier, or None (rules only) when it has no key.
    Only builds a client: no request is made."""
    key = settings.ai_api_key
    if settings.ai_provider == "anthropic" and key is not None:
        return make_claude_classifier(
            key.get_secret_value(), settings.ai_model, settings.ai_timeout_seconds
        )
    if settings.ai_provider == "nvidia" and key is not None:
        return make_openai_compatible_classifier(
            provider=AI_PROVIDER_LABELS["nvidia"],
            api_key=key.get_secret_value(),
            model=settings.nvidia_model,
            base_url=settings.nvidia_base_url,
            timeout=settings.ai_timeout_seconds,
        )
    if settings.ai_provider is not None:
        logger.warning(
            "AI_PROVIDER=%s, but %s_API_KEY is empty: the AI layer is off",
            settings.ai_provider,
            settings.ai_provider.upper(),
        )
    return None


def make_pricing(settings: Settings) -> AIPricing | None:
    """Prices to estimate each import's cost. NVIDIA's hosted API has none configured here,
    so its cost is not estimated (recorded as 0) instead of borrowing Claude's prices."""
    if settings.ai_provider == "nvidia":
        return None
    return AIPricing(settings.ai_input_price_per_mtok, settings.ai_output_price_per_mtok)


def make_categorizer(
    settings: Settings, classifier: TransactionClassifier | None = None
) -> Categorizer:
    """The pipeline the API and the Telegram bot share. Tests pass a fake classifier."""
    if classifier is None:
        classifier = make_classifier(settings)
    return Categorizer(classifier, settings.ai_min_confidence, settings.ai_batch_size)
