from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from financas.categorization.ai import TransactionClassifier, make_claude_classifier
from financas.categorization.pipeline import Categorizer
from financas.config import Settings, get_settings
from financas.db import make_engine, make_session_factory
from financas.deps import AppContext
from financas.routers import auth, dashboard, imports, meta, rules, transactions
from financas.services.imports import AIPricing

DESCRIPTION = """
Importa extratos bancários (OFX e CSV), categoriza cada transação com regras e, só quando
elas não resolvem, com IA (Claude). O usuário revisa e as correções viram regras.

Para testar aqui: clique em **Authorize** e entre com `demo@example.com` / `demo1234`.
"""


def create_app(
    settings: Settings | None = None, classifier: TransactionClassifier | None = None
) -> FastAPI:
    """Build the app. Tests pass their own settings and a fake classifier."""
    settings = settings or get_settings()
    if classifier is None and settings.anthropic_api_key is not None:
        classifier = make_claude_classifier(
            settings.anthropic_api_key.get_secret_value(), settings.ai_model
        )

    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        title="Finanças com IA", description=DESCRIPTION, version="0.1.0", lifespan=lifespan
    )
    app.state.context = AppContext(
        settings=settings,
        session_factory=make_session_factory(engine),
        categorizer=Categorizer(classifier, settings.ai_min_confidence, settings.ai_batch_size),
        pricing=AIPricing(settings.ai_input_price_per_mtok, settings.ai_output_price_per_mtok),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (auth, meta, imports, transactions, rules, dashboard):
        app.include_router(module.router)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
