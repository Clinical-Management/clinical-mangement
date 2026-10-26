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
    # Public address of this API (receipt links point straight at the PDF)
    api_public_url: str = "http://localhost:8000"
    patient_link_days: int = 30
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

    # Notifications. Without a provider, WhatsApp/SMS messages are recorded as "not configured" and staff
    # can still share links from their own phone. WhatsApp uses the Cloud API with an approved template
    # that has one body variable; SMS uses Twilio.
    whatsapp_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_template: str = "clinic_message"
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from: str | None = None
    # Background sender for reminders and scheduled messages (off in tests, which call it directly)
    notifications_worker: bool = True
    notifications_interval_seconds: int = 30

    # Report uploads (stored in MongoDB GridFS)
    report_max_mb: int = 25

    # Comma-separated in the env var, e.g. "http://localhost:5173,https://app.vercel.app"
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cors_origin_regex(self) -> str | None:
        """Outside production, the dev frontend on any local port (Vite moves to 5174... when 5173 is busy)."""
        if self.app_env.lower() in {"production", "prod"}:
            return None
        return r"http://(localhost|127\.0\.0\.1)(:\d+)?"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
