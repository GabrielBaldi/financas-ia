from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

type AIProvider = Literal["anthropic", "nvidia"]

AI_PROVIDER_LABELS: dict[AIProvider, str] = {"anthropic": "Anthropic", "nvidia": "NVIDIA"}


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./financas.db"
    cors_origins: str = "http://localhost:5102"
    token_ttl_hours: int = 24 * 7

    # Which AI categorizes what the rules cannot. Left empty, it is picked from the keys:
    # Claude with ANTHROPIC_API_KEY, else NVIDIA with NVIDIA_API_KEY, else no AI (rules only).
    ai_provider: AIProvider | None = None
    ai_min_confidence: float = 0.7
    ai_batch_size: int = 100
    ai_timeout_seconds: float = Field(default=60.0, gt=0)

    # Anthropic (Claude), the default provider.
    anthropic_api_key: SecretStr | None = None
    ai_model: str = "claude-haiku-5-5"
    # Claude's USD per million tokens, used only to estimate the cost of each import.
    ai_input_price_per_mtok: float = 0.10
    ai_output_price_per_mtok: float = 0.50

    # NVIDIA's hosted API (build.nvidia.com), OpenAI-compatible. No price is configured for it.
    nvidia_api_key: SecretStr | None = None
    nvidia_model: str = "minimaxai/minimax-m3.1-flash"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"

    # The Telegram bot (python -m financas.telegram_bot). The API itself never uses the token.
    telegram_bot_token: SecretStr | None = None
    # Only tests and the local end-to-end harness point this at a fake Telegram server.
    telegram_api_url: str = "https://api.telegram.org"

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        """Hosted Postgres providers hand out postgres:// URLs; SQLAlchemy needs the driver name."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url

    @field_validator("anthropic_api_key", "nvidia_api_key", "telegram_bot_token")
    @classmethod
    def blank_key_means_no_key(cls, key: SecretStr | None) -> SecretStr | None:
        if key is None or not key.get_secret_value().strip():
            return None
        return key

    @field_validator("ai_provider", mode="before")
    @classmethod
    def blank_provider_means_automatic(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower() or None
        return value

    @model_validator(mode="after")
    def pick_ai_provider(self) -> Self:
        """An explicit AI_PROVIDER wins, even without its key (then the AI stays off rather
        than sending transactions to a provider nobody chose). Otherwise Claude comes first."""
        if self.ai_provider is None:
            if self.anthropic_api_key is not None:
                self.ai_provider = "anthropic"
            elif self.nvidia_api_key is not None:
                self.ai_provider = "nvidia"
        return self

    @property
    def ai_api_key(self) -> SecretStr | None:
        """The chosen provider's key. None means the AI layer is off."""
        if self.ai_provider == "anthropic":
            return self.anthropic_api_key
        if self.ai_provider == "nvidia":
            return self.nvidia_api_key
        return None

    @property
    def active_ai_model(self) -> str | None:
        """The chosen provider's model, or None when no provider is chosen."""
        if self.ai_provider == "anthropic":
            return self.ai_model
        if self.ai_provider == "nvidia":
            return self.nvidia_model
        return None

    @property
    def ai_enabled(self) -> bool:
        return self.ai_api_key is not None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
