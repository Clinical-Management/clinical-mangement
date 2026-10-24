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
    # Sessions: staff are signed out after this much inactivity (the app refreshes the token while in use)
    # and must re-enter their password after the absolute limit; patients stay signed in for a week
    staff_idle_minutes: int = 30
    staff_session_max_hours: int = 12
    patient_session_minutes: int = 60 * 24 * 7
    # Staff must set up an authenticator app (TOTP) before their first sign-in completes
    staff_mfa_required: bool = True

    # Encryption at rest for uploaded files and secrets (32 bytes, base64; see app/core/crypto.py)
    data_encryption_key: str | None = None
    # Signs audit log entries so edits and deletions are detectable (falls back to JWT_SECRET)
    audit_signing_key: str | None = None

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

    # Case summary drafting
    case_summary_model: str = "claude-opus-5-5"
    case_summary_effort: str = "medium"

    # Prescriptions: signing key for the verification QR (falls back to JWT_SECRET), public app URL
    # used in QR codes and patient links, and optional SMTP for emailing PDFs
    prescription_signing_key: str | None = None
    frontend_url: str = "http://localhost:5173"
    patient_link_days: int = 30
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

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
