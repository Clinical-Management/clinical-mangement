from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Clinical Management API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "clinical_management"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # All appointment dates/times are clinic-local
    clinic_timezone: str = "Asia/Kolkata"
    booking_horizon_days: int = 90

    # Voicebot patient history (Claude). The key may also come from ANTHROPIC_API_KEY
    # in the process environment or an `ant auth login` profile.
    anthropic_api_key: str | None = None
    history_model: str = "claude-opus-5-5"
    history_effort: str = "low"  # per-turn latency matters for a spoken conversation
    history_link_minutes: int = 120  # lifetime of kiosk / phone links

    # Report summarization (Claude reads the report pages)
    report_model: str = "claude-opus-5-5"
    report_effort: str = "high"  # accuracy over speed: values feed clinical decisions

    # Report uploads (stored in MongoDB GridFS)
    report_max_mb: int = 25

    # Comma-separated in the env var, e.g. "http://localhost:5173,https://app.vercel.app"
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
