from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./financas.db"
    cors_origins: str = "http://localhost:5102"
    token_ttl_hours: int = 24 * 7

    anthropic_api_key: SecretStr | None = None
    ai_model: str = "claude-haiku-5-5"
    ai_min_confidence: float = 0.7
    ai_batch_size: int = 100
    # USD per million tokens, used only to estimate the cost of each import.
    ai_input_price_per_mtok: float = 0.10
    ai_output_price_per_mtok: float = 0.50

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        """Hosted Postgres providers hand out postgres:// URLs; SQLAlchemy needs the driver name."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url

    @field_validator("anthropic_api_key")
    @classmethod
    def blank_key_means_no_key(cls, key: SecretStr | None) -> SecretStr | None:
        if key is None or not key.get_secret_value().strip():
            return None
        return key

    @property
    def ai_enabled(self) -> bool:
        return self.anthropic_api_key is not None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
