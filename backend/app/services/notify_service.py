"""Notification outbox: messages are queued (now or for later) and sent by a background worker.

Channels: WhatsApp (Cloud API template), SMS (Twilio), email (SMTP) and the patient app inbox. A failed or
unconfigured WhatsApp message falls back to SMS. Everything sent is kept, so staff can see what went out."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.core import clock
from app.core.config import settings
from app.notifications.templates import SUBJECTS
from app.services import messaging

log = logging.getLogger(__name__)

APP = "app"
CHANNELS = ("whatsapp", "sms", "email", APP)


def _now() -> datetime:
    now = clock.clinic_now().astimezone(timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def prefs(patient: dict) -> dict:
    c = patient.get("communication") or {}
    return {"language": c.get("language", "en"), "channels": c.get("channels") or ["whatsapp", APP], "reminders": c.get("reminders", True)}


def _address(patient: dict, channel: str) -> str | None:
    if channel in ("whatsapp", "sms"):
        return patient.get("phone")
    if channel == "email":
        return patient.get("email")
    return str(patient["managed_by"]) if patient.get("managed_by") else None  # app inbox: the account


async def queue(
    db: AsyncDatabase,
    patient: dict,
    *,
    kind: str,
    text: str,
    channels: list[str] | None = None,
    at: datetime | None = None,
    appointment_id: ObjectId | None = None,
    ref: dict | None = None,
) -> list[dict]:
    """One message per channel the patient chose (or `channels`), skipping channels with no address."""
    p = prefs(patient)
    wanted = [c for c in (channels or p["channels"]) if c in CHANNELS]
    batch = ObjectId()  # the same message on several channels
    docs = []
    for channel in dict.fromkeys(wanted):
        to = _address(patient, channel)
        if not to:
            continue
        docs.append({
            "batch": batch, "patient_id": patient["patient_id"], "appointment_id": appointment_id, "kind": kind, "channel": channel, "to": to,
            "language": p["language"], "text": text, "subject": SUBJECTS.get(kind, "Message from the clinic"),
            "scheduled_at": at or _now(), "status": "scheduled", "attempts": 0, "ref": ref or {},
            "created_at": _now(), "sent_at": None, "error": None, "read_at": None,
        })
    if docs:
        await db.notifications.insert_many(docs)
    return docs


async def cancel(db: AsyncDatabase, query: dict) -> int:
    result = await db.notifications.update_many({**query, "status": "scheduled"}, {"$set": {"status": "cancelled"}})
    return result.modified_count


# --- providers -------------------------------------------------------------------------


class NotConfigured(Exception):
    pass


async def _send_whatsapp(to: str, text: str, lang: str) -> str:
    if not (settings.whatsapp_token and settings.whatsapp_phone_number_id):
        raise NotConfigured("WhatsApp is not set up")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"https://graph.facebook.com/v21.0/{settings.whatsapp_phone_number_id}/messages",
            headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": messaging.phone_digits(to),
                "type": "template",
                "template": {"name": settings.whatsapp_template, "language": {"code": lang},
                             "components": [{"type": "body", "parameters": [{"type": "text", "text": text}]}]},
            },
        )
    r.raise_for_status()
    return (r.json().get("messages") or [{}])[0].get("id", "")


async def _send_sms(to: str, text: str) -> str:
    if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from):
        raise NotConfigured("SMS is not set up")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            data={"To": "+" + messaging.phone_digits(to), "From": settings.twilio_from, "Body": text},
        )
    r.raise_for_status()
    return r.json().get("sid", "")


async def _send_email(to: str, subject: str, text: str) -> str:
    if not messaging.smtp_configured():
        raise NotConfigured("Email is not set up")
    await asyncio.to_thread(messaging.smtp_send, to, subject, text)
    return ""


async def _deliver(n: dict) -> str:
    if n["channel"] == "whatsapp":
        return await _send_whatsapp(n["to"], n["text"], n["language"])
    if n["channel"] == "sms":
        return await _send_sms(n["to"], n["text"])
    if n["channel"] == "email":
        return await _send_email(n["to"], n["subject"], n["text"])
    return ""  # app inbox: stored is delivered


# --- sending -----------------------------------------------------------------------------


async def _send_one(db: AsyncDatabase, n: dict) -> None:
    try:
        ref = await _deliver(n)
        await db.notifications.update_one({"_id": n["_id"]}, {"$set": {"status": "sent", "sent_at": _now(), "provider_ref": ref}})
        return
    except NotConfigured as exc:
        status, error = "not_configured", str(exc)
    except Exception as exc:  # provider errors vary widely
        log.warning("Notification %s failed: %s", n["_id"], exc)
        status, error = "failed", str(exc)[:300]
    await db.notifications.update_one({"_id": n["_id"]}, {"$set": {"status": status, "error": error}})
    sms_in_batch = await db.notifications.find_one({"batch": n.get("batch"), "channel": "sms"}) if n.get("batch") else None
    if n["channel"] == "whatsapp" and not n.get("fallback_of") and not sms_in_batch:
        # WhatsApp didn't go through: try SMS instead
        sms = {k: v for k, v in n.items() if k != "_id"}
        sms.update(channel="sms", status="scheduled", attempts=0, error=None, scheduled_at=_now(), fallback_of=n["_id"], created_at=_now())
        await db.notifications.insert_one(sms)


async def dispatch_due(db: AsyncDatabase, limit: int = 200) -> int:
    """Send messages whose time has come. Safe to run from several workers (each message is claimed once)."""
    sent = 0
    for _ in range(limit):
        n = await db.notifications.find_one_and_update(
            {"status": "scheduled", "scheduled_at": {"$lte": _now()}},
            {"$set": {"status": "sending"}, "$inc": {"attempts": 1}},
            sort=[("scheduled_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if not n:
            break
        await _send_one(db, n)
        sent += 1
    # a worker that died mid-send leaves "sending" behind; retry those after a while
    await db.notifications.update_many(
        {"status": "sending", "scheduled_at": {"$lte": _now() - timedelta(minutes=10)}, "attempts": {"$lt": 3}}, {"$set": {"status": "scheduled"}}
    )
    return sent


async def run_worker(get_db) -> None:
    """Started with the app: queue due reminders and nudges, then send whatever is due."""
    from app.services import reminder_service

    while True:
        try:
            db = get_db()
            await reminder_service.queue_due(db)
            await dispatch_due(db)
        except Exception:
            log.exception("notification worker tick failed")
        await asyncio.sleep(settings.notifications_interval_seconds)


# --- reading -------------------------------------------------------------------------------


async def inbox(db: AsyncDatabase, user: dict, limit: int = 50) -> list[dict]:
    """The patient app's messages."""
    return await db.notifications.find({"channel": APP, "to": str(user["_id"]), "status": "sent"}).sort("sent_at", -1).to_list(limit)


async def mark_read(db: AsyncDatabase, user: dict) -> None:
    await db.notifications.update_many({"channel": APP, "to": str(user["_id"]), "read_at": None}, {"$set": {"read_at": _now()}})


async def log_for(db: AsyncDatabase, *, patient_id: str | None = None, kind: str | None = None, status: str | None = None, limit: int = 200) -> list[dict]:
    q: dict = {}
    if patient_id:
        q["patient_id"] = patient_id.upper()
    if kind:
        q["kind"] = kind
    if status:
        q["status"] = status
    return await db.notifications.find(q).sort("scheduled_at", -1).to_list(limit)
