from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_secret_key: str = "dev-secret-change-me"

    database_url: str = "sqlite:///./data/aristeus.db"

    allowed_origins: str = "http://localhost:5173"

    openrouter_api_key: str = ""
    openrouter_default_model: str = "google/gemini-2.0-flash-exp:free"
    # Comma-separated fallback chain, tried in order after default fails
    openrouter_fallback_models: str = "meta-llama/llama-3.3-70b-instruct:free"

    @property
    def model_chain(self) -> list[str]:
        """All models to try in order: default first, then each fallback."""
        fallbacks = [m.strip() for m in self.openrouter_fallback_models.split(",") if m.strip()]
        return [self.openrouter_default_model] + fallbacks

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Aristeus <noreply@example.com>"

    public_frontend_url: str = "http://localhost:5173"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
