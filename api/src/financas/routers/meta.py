from fastapi import APIRouter

from financas.categories import CATEGORY_LABELS
from financas.deps import ContextDep
from financas.schemas import CategoryOut, MetaOut

router = APIRouter(tags=["meta"])


@router.get("/meta")
def meta(context: ContextDep) -> MetaOut:
    """Public: the category list and whether the AI layer is on, with which provider and model."""
    ai_enabled = context.categorizer.ai_enabled
    return MetaOut(
        ai_enabled=ai_enabled,
        ai_provider=context.settings.ai_provider if ai_enabled else None,
        ai_model=context.settings.active_ai_model if ai_enabled else None,
        categories=[CategoryOut(slug=slug, label=label) for slug, label in CATEGORY_LABELS.items()],
    )
