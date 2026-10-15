"""Clinic-local time. Call through the module (`clock.clinic_now()`) so tests can patch it."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def clinic_now() -> datetime:
    return datetime.now(ZoneInfo(settings.clinic_timezone))


def clinic_today() -> date:
    return clinic_now().date()


def to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def from_minutes(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
