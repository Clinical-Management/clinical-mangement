"""Low-level message helpers shared by prescriptions, receipts and reminders: email over SMTP and
device share links (wa.me / sms: / mailto:) for when no messaging provider is configured."""

import hashlib
import re
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import quote

from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings
from app.core.errors import Forbidden, NotFound


def phone_digits(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return "91" + digits if len(digits) == 10 else digits  # Indian mobile without country code


def whatsapp_url(phone: str, text: str) -> str:
    return f"https://wa.me/{phone_digits(phone)}?text={quote(text)}"


def sms_url(phone: str, text: str) -> str:
    return f"sms:{phone_digits(phone)}?body={quote(text)}"


def mailto_url(email: str, subject: str, text: str) -> str:
    return f"mailto:{email}?subject={quote(subject)}&body={quote(text)}"


def smtp_configured() -> bool:
    return bool(settings.smtp_host)


def smtp_send(to: str, subject: str, text: str, attachments: list[tuple[bytes, str]] = ()) -> None:
    """Blocking; call through asyncio.to_thread. `attachments` are (pdf bytes, filename)."""
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_username
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    for data, filename in attachments:
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=filename)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(msg)


# --- expiring links for patients without an app account ------------------------


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_link_token(db: AsyncDatabase, kind: str, ref_id, days: int | None = None) -> str:
    token = secrets.token_urlsafe(18)
    now = datetime.now(timezone.utc)
    await db.share_links.insert_one(
        {"kind": kind, "ref_id": ref_id, "token_hash": _hash(token), "expires_at": now + timedelta(days=days or settings.patient_link_days), "created_at": now}
    )
    return token


async def check_link_token(db: AsyncDatabase, kind: str, ref_id, token: str) -> None:
    link = await db.share_links.find_one({"kind": kind, "ref_id": ref_id, "token_hash": _hash(token)})
    if not link:
        raise NotFound("This link is not valid")
    expires = link["expires_at"] if link["expires_at"].tzinfo else link["expires_at"].replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise Forbidden("This link has expired. Please ask the clinic for a new one.")
