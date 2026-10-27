"""Prescriptions: autosaved draft -> safety checks -> finalized, signed, immutable versions.

Editing after finalizing starts the next version's draft; earlier versions stay viewable and
verifiable (the QR on an old PDF reports that it has been superseded).
"""

import asyncio
import hashlib
import logging
import secrets
from datetime import date, datetime, timedelta, timezone

from bson import ObjectId
from gridfs import AsyncGridFSBucket
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.ai.client import EngineError
from app.core.config import settings
from app.core.errors import Conflict, Forbidden, Invalid, NotFound
from app.prescribing import checks as rx_checks, pdf as rx_pdf, signing, translate as tr
from app.schemas.common import parse_object_id
from app.schemas.prescription import FinalizeIn, PrescriptionIn
from app.services import case_summary_service, messaging, patient_service, scheduling_service

log = logging.getLogger(__name__)

EMPTY = {"medicines": [], "investigations": [], "advice": "", "diet_lifestyle": "", "referral": None, "follow_up": None, "summary_sections": {}}
CONTENT_KEYS = ("medicines", "investigations", "advice", "diet_lifestyle", "referral", "follow_up", "summary_sections")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- draft -------------------------------------------------------------------


async def _patient_context(db: AsyncDatabase, appt: dict) -> dict:
    patient = await patient_service.get_patient(db, appt["patient_id"])
    medical = patient.get("medical") or {}
    vitals = await db.vitals.find_one({"appointment_id": appt["_id"], "weight_kg": {"$ne": None}}, sort=[("recorded_at", -1)]) or \
        await db.vitals.find_one({"patient_id": appt["patient_id"], "weight_kg": {"$ne": None}}, sort=[("recorded_at", -1)])
    return {
        "patient": patient,
        "allergies": [a["substance"] for a in medical.get("allergies", [])],
        "current_meds": [m["name"] for m in medical.get("current_medications", [])],
        "age": patient_service.current_age(patient),
        "weight_kg": vitals["weight_kg"] if vitals else None,
    }


async def run_checks(db: AsyncDatabase, appt: dict, medicines: list[dict]) -> list[dict]:
    ctx = await _patient_context(db, appt)
    return await rx_checks.run_checks(
        db, medicines, allergies=ctx["allergies"], current_meds=ctx["current_meds"], age=ctx["age"], weight_kg=ctx["weight_kg"]
    )


async def get(db: AsyncDatabase, appt: dict) -> dict:
    doc = await db.prescriptions.find_one({"appointment_id": appt["_id"]}) or {}
    content = {**EMPTY, **{k: doc[k] for k in CONTENT_KEYS if k in doc}}
    current = doc.get("current_version", 0)
    status = doc.get("status", "draft")
    return {
        **content,
        "appointment_id": str(appt["_id"]),
        "patient_id": appt["patient_id"],
        "status": status,
        "current_version": current,
        "editing_version": current if status == "final" else current + 1,
        "checks": await run_checks(db, appt, content["medicines"]),
        "updated_at": doc.get("updated_at"),
        "updated_by_role": doc.get("updated_by_role"),
    }


def _with_follow_up_date(appt: dict, body: dict) -> dict:
    follow = body.get("follow_up")
    if follow and follow.get("in_days") is not None and not follow.get("date"):
        follow["date"] = (date.fromisoformat(appt["date"]) + timedelta(days=follow["in_days"])).isoformat()
    return body


async def save(db: AsyncDatabase, appt: dict, data: PrescriptionIn, actor: dict) -> dict:
    """Autosaved as a whole. Edits after finalizing start the next version's draft."""
    body = _with_follow_up_date(appt, data.model_dump(mode="json"))
    existing = await db.prescriptions.find_one({"appointment_id": appt["_id"]})
    if existing and existing.get("status") == "final" and all(existing.get(k) == body[k] for k in CONTENT_KEYS):
        return await get(db, appt)  # nothing changed: stay finalized
    await db.prescriptions.find_one_and_update(
        {"appointment_id": appt["_id"]},
        {
            "$set": {**body, "status": "draft", "updated_at": _now(), "updated_by": actor["_id"], "updated_by_role": actor["role"]},
            "$setOnInsert": {"patient_id": appt["patient_id"], "doctor_id": appt["doctor_id"], "current_version": 0},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return await get(db, appt)


# --- finalize & versions -----------------------------------------------------


async def clinic_settings(db: AsyncDatabase) -> dict:
    doc = await db.settings.find_one({"_id": "clinic"}) or {}
    return {"name": doc.get("name") or "Clinical Management", **{k: doc.get(k) for k in ("address", "phone", "email", "registration", "gstin", "upi_id")}}


async def _letterhead(db: AsyncDatabase, appt: dict) -> dict:
    clinic = await clinic_settings(db)
    doctor = await scheduling_service.get_doctor(db, appt["doctor_id"])
    return {
        "clinic_name": clinic["name"], "address": clinic["address"], "phone": clinic["phone"], "email": clinic["email"],
        "clinic_registration": clinic["registration"], "doctor_name": doctor["full_name"],
        "specialization": doctor.get("specialization"), "qualifications": doctor.get("qualifications"),
        "registration_number": doctor.get("registration_number"), "registration_council": doctor.get("registration_council"),
    }


def _signed_payload(version: dict) -> dict:
    keys = ("public_id", "version", "visit_date", "content", "case_summary", "letterhead", "patient")
    return {**{k: version[k] for k in keys}, "finalized_at": version["finalized_at"].isoformat()}


async def finalize(db: AsyncDatabase, appt: dict, body: FinalizeIn, actor: dict) -> dict:
    current = await get(db, appt)
    if current["status"] == "final":
        raise Conflict("Already finalized - edit the prescription to start a new version")
    if not (current["medicines"] or current["investigations"] or current["advice"].strip() or current["referral"]):
        raise Invalid("Add at least a medicine, an investigation, advice or a referral before finalizing")
    warnings = [c for c in current["checks"] if c["severity"] in ("high", "moderate")]
    if warnings and not body.acknowledged:
        raise Conflict({"code": "checks_need_acknowledgement", "message": "Review the prescription warnings before finalizing", "checks": warnings})
    if any(c["severity"] == "high" for c in warnings) and not (body.override_reason or "").strip():
        raise Invalid("A reason is required to finalize with high-severity warnings")

    ctx = await _patient_context(db, appt)
    patient = ctx["patient"]
    content = {k: current[k] for k in CONTENT_KEYS}
    number = current["current_version"] + 1
    version = {
        "appointment_id": appt["_id"],
        "patient_id": appt["patient_id"],
        "doctor_id": appt["doctor_id"],
        "version": number,
        "public_id": signing.public_id(),
        "visit_date": appt["date"],
        "content": content,
        "case_summary": await case_summary_service.finalized_sections(db, appt, content["summary_sections"]),
        "letterhead": await _letterhead(db, appt),
        "patient": {"name": patient["full_name"], "age": ctx["age"], "gender": patient["gender"],
                    "patient_id": patient["patient_id"], "allergies": ctx["allergies"]},
        "checks": current["checks"],
        "override_reason": (body.override_reason or "").strip() or None,
        # MongoDB keeps milliseconds: round now so the signed timestamp survives the round trip
        "finalized_at": (now := _now()).replace(microsecond=now.microsecond // 1000 * 1000),
        "finalized_by": actor["_id"],
        "finalized_by_role": actor["role"],
        "superseded_by": None,
        "translations": {},
    }
    version["signature"] = signing.sign(_signed_payload(version))
    await db.prescription_versions.insert_one(version)
    await db.prescription_versions.update_many(
        {"appointment_id": appt["_id"], "_id": {"$ne": version["_id"]}, "superseded_by": None},
        {"$set": {"superseded_by": version["_id"], "superseded_at": _now()}},
    )
    await db.prescriptions.update_one({"appointment_id": appt["_id"]}, {"$set": {"status": "final", "current_version": number, "nudged_at": None}})
    # the advised follow-up goes straight into the calendar (nearest free slot on or after the date)
    from app.services import reminder_service

    follow = content.get("follow_up") or {}
    await reminder_service.sync_follow_up(db, appt, date.fromisoformat(str(follow["date"])[:10]) if follow.get("date") else None, actor)
    return version


def version_view(v: dict) -> dict:
    return {**v, "superseded": v.get("superseded_by") is not None}


async def list_versions(db: AsyncDatabase, appt: dict) -> list[dict]:
    return [version_view(v) for v in await db.prescription_versions.find({"appointment_id": appt["_id"]}).sort("version", -1).to_list(None)]


async def get_version(db: AsyncDatabase, version_id: str) -> dict:
    oid = parse_object_id(version_id)
    v = oid and await db.prescription_versions.find_one({"_id": oid})
    if not v:
        raise NotFound("Prescription version not found")
    return v


# --- PDF ---------------------------------------------------------------------


async def _translations(db: AsyncDatabase, version: dict, lang: str) -> dict[str, str]:
    """AI translation of free text for the patient copy, cached per version. Only with AI consent;
    otherwise the patient copy uses the fixed phrases and keeps free text in English."""
    if lang == "en":
        return {}
    if lang in version.get("translations", {}):
        return version["translations"][lang]
    patient = await patient_service.get_patient(db, version["patient_id"])
    texts = tr.free_texts(version["content"], version["case_summary"])
    if not texts or not patient["consent"].get("ai_processing"):
        return {}
    try:
        mapping = dict(zip(texts, await tr.translate_free_text(texts, lang)))
    except EngineError:
        return {}  # not cached, so it is retried next time
    await db.prescription_versions.update_one({"_id": version["_id"]}, {"$set": {f"translations.{lang}": mapping}})
    return mapping


def verify_url(version: dict) -> str:
    return f"{settings.frontend_url.rstrip('/')}/verify/{version['public_id']}"


async def render_pdf(db: AsyncDatabase, version: dict, *, lang: str, copy: str) -> bytes:
    signature = None
    profile = await db.doctor_profiles.find_one({"_id": version["doctor_id"]}) or {}
    if profile.get("signature_file_id"):
        stream = await AsyncGridFSBucket(db, bucket_name="signatures").open_download_stream(profile["signature_file_id"])
        signature = await stream.read()
    translations = await _translations(db, version, lang)
    return await asyncio.to_thread(
        rx_pdf.render, version, lang=lang, copy=copy, translations=translations, signature_png=signature, verify_url=verify_url(version)
    )


# --- verification (public) ---------------------------------------------------


async def verify_public(db: AsyncDatabase, public_id: str) -> dict:
    """What a pharmacist sees after scanning the QR: authenticity and currency, minimal personal data."""
    v = await db.prescription_versions.find_one({"public_id": public_id.upper()})
    if not v:
        raise NotFound("No prescription with this code")
    name_parts = v["patient"]["name"].split()
    newer = await db.prescription_versions.find_one({"_id": v["superseded_by"]}) if v.get("superseded_by") else None
    return {
        "public_id": v["public_id"],
        "valid": signing.verify(_signed_payload(v), v["signature"]),
        "current": newer is None,
        "superseded_by_version": newer["version"] if newer else None,
        "version": v["version"],
        "date": v["visit_date"],
        "finalized_at": v["finalized_at"],
        "clinic_name": v["letterhead"]["clinic_name"],
        "doctor_name": v["letterhead"]["doctor_name"],
        "registration_number": v["letterhead"].get("registration_number"),
        "patient_initials": "".join(p[0].upper() for p in name_parts if p)[:3],
        "patient_age": v["patient"]["age"],
        "patient_gender": v["patient"]["gender"],
        "medicines": [
            {"name": m["name"], "dose": m.get("dose"), "frequency": m.get("frequency"), "duration": m.get("duration")}
            for m in v["content"]["medicines"]
        ],
    }


# --- delivery ----------------------------------------------------------------


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_link(db: AsyncDatabase, version: dict, lang: str) -> str:
    token = secrets.token_urlsafe(18)
    await db.rx_links.insert_one(
        {"version_id": version["_id"], "token_hash": _hash(token), "language": lang,
         "expires_at": _now() + timedelta(days=settings.patient_link_days), "created_at": _now()}
    )
    return f"{settings.frontend_url.rstrip('/')}/rx/{version['public_id']}?token={token}&lang={lang}"


async def version_for_link(db: AsyncDatabase, public_id: str, token: str) -> dict:
    v = await db.prescription_versions.find_one({"public_id": public_id.upper()})
    link = v and await db.rx_links.find_one({"version_id": v["_id"], "token_hash": _hash(token)})
    if not link:
        raise NotFound("This prescription link is not valid")
    expires = link["expires_at"] if link["expires_at"].tzinfo else link["expires_at"].replace(tzinfo=timezone.utc)
    if expires < _now():
        raise Forbidden("This prescription link has expired. Please ask the clinic for a new one.")
    return v


async def deliver(db: AsyncDatabase, version: dict, *, channel: str, to: str | None, lang: str, actor: dict) -> dict:
    """Print / WhatsApp / SMS / email / patient app. WhatsApp and SMS open on this device with a secure
    link (no messaging provider is configured); email is sent with the PDF when SMTP is set up."""
    patient = await patient_service.get_patient(db, version["patient_id"])
    clinic = version["letterhead"]["clinic_name"]
    record = {"version_id": version["_id"], "appointment_id": version["appointment_id"], "channel": channel, "language": lang,
              "to": None, "link": None, "share_url": None, "detail": None, "at": _now(), "by": actor["_id"], "by_role": actor["role"]}

    if channel == "print":
        record.update(status="recorded", detail="Printed / downloaded")
    elif channel == "patient_app":
        if patient.get("managed_by"):
            record.update(status="published", detail="Visible in the patient's app")
        else:
            record.update(status="failed", detail="This patient has no app account; use WhatsApp, SMS or email")
    else:
        link = await issue_link(db, version, lang)
        message = f"{clinic}: your prescription from {version['letterhead']['doctor_name']} ({version['visit_date']}). Open: {link}"
        record["link"] = link
        if channel in ("whatsapp", "sms"):
            phone = to or patient["phone"]
            record["to"] = phone
            record["share_url"] = (
                messaging.whatsapp_url(phone, message) if channel == "whatsapp" else messaging.sms_url(phone, message)
            )
            record.update(status="link_ready", detail="Opens on this device to send")
        else:  # email
            email = to or patient.get("email")
            if not email:
                raise Invalid("No email address for this patient")
            record["to"] = email
            if messaging.smtp_configured():
                try:
                    data = await render_pdf(db, version, lang=lang, copy="patient")
                    await asyncio.to_thread(messaging.smtp_send, email, f"Your prescription - {clinic}", message, [(data, f"{version['public_id']}.pdf")])
                    record.update(status="sent", detail="Emailed with the PDF attached")
                except Exception as exc:  # SMTP errors vary widely
                    log.warning("Prescription email failed: %s", exc)
                    record.update(status="failed", detail="Email could not be sent; try again or share the link")
            else:
                record["share_url"] = messaging.mailto_url(email, f"Your prescription - {clinic}", message)
                record.update(status="link_ready", detail="Email server not configured: opens your mail app with the link")
    await db.rx_deliveries.insert_one(record)
    return record


async def deliveries(db: AsyncDatabase, appt: dict) -> list[dict]:
    return await db.rx_deliveries.find({"appointment_id": appt["_id"]}).sort("at", -1).to_list(100)
