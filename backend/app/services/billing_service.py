import secrets
from datetime import datetime, timezone

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.core.errors import Conflict, Invalid
from app.schemas.appointment import PaymentStatus
from app.schemas.billing import BillIn
from app.services import appointment_service, scheduling_service

VISIT_LABELS = {"new": "New", "follow_up": "Follow-up", "returning": "Returning"}
CONSULTATION_ID = "consultation"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _consultation_item(appt: dict, doctor: dict) -> tuple[dict, bool]:
    fee = (doctor.get("fees") or {}).get(appt["visit_type"])
    item = {
        "id": CONSULTATION_ID,
        "description": f"Consultation - {VISIT_LABELS[appt['visit_type']]} visit ({doctor['full_name']})",
        "amount": fee or 0,
        "kind": "consultation",
        "auto": True,
    }
    return item, fee is None


def _view(bill: dict, appt: dict) -> dict:
    subtotal = sum(i["amount"] for i in bill["items"])
    return {
        **bill,
        "appointment_id": str(appt["_id"]),
        "patient_id": appt["patient_id"],
        "visit_type": appt["visit_type"],
        "subtotal": subtotal,
        "total": max(0, subtotal - bill["discount"]),
        # the appointment's payment status is the source of truth (it drives follow-up visits)
        "payment_status": appt["payment_status"],
    }


async def get_bill(db: AsyncDatabase, appt: dict) -> dict:
    """The visit's bill, created on first view with the consultation fee for the visit type.
    While unpaid, an untouched auto line follows changes to the visit type."""
    doctor = await scheduling_service.get_doctor(db, appt["doctor_id"])
    auto_item, fee_missing = _consultation_item(appt, doctor)
    bill = await db.bills.find_one({"appointment_id": appt["_id"]})
    if bill is None:
        bill = {
            "appointment_id": appt["_id"],
            "patient_id": appt["patient_id"],
            "items": [auto_item],
            "discount": 0,
            "payment_mode": None,
            "paid_at": None,
            "waive_reason": None,
            "created_at": _now(),
        }
        await db.bills.insert_one(bill)
    elif appt["payment_status"] == PaymentStatus.UNPAID.value:
        items = [auto_item if i.get("auto") and i["id"] == CONSULTATION_ID else i for i in bill["items"]]
        if items != bill["items"]:
            bill = await db.bills.find_one_and_update(
                {"_id": bill["_id"]}, {"$set": {"items": items}}, return_document=ReturnDocument.AFTER
            )
    return {**_view(bill, appt), "fee_missing": fee_missing}


async def save_bill(db: AsyncDatabase, appt: dict, data: BillIn) -> dict:
    if appt["payment_status"] != PaymentStatus.UNPAID.value:
        raise Conflict("This bill is already settled")
    current = await get_bill(db, appt)
    previous = {i["id"]: i for i in current["items"]}
    items = []
    for item in data.items:
        row = item.model_dump()
        row["id"] = row["id"] or secrets.token_hex(4)
        old = previous.get(row["id"])
        # a line stays "auto" only while nobody has changed it
        row["auto"] = bool(old and old.get("auto") and old["amount"] == row["amount"] and old["description"] == row["description"])
        items.append(row)
    subtotal = sum(i["amount"] for i in items)
    if data.discount > subtotal:
        raise Invalid("Discount cannot be more than the total")
    await db.bills.update_one({"appointment_id": appt["_id"]}, {"$set": {"items": items, "discount": data.discount}})
    return await get_bill(db, appt)


async def pay(db: AsyncDatabase, appt: dict, mode: str, actor: dict) -> dict:
    if appt["payment_status"] != PaymentStatus.UNPAID.value:
        raise Conflict("This bill is already settled")
    await get_bill(db, appt)  # make sure it exists
    await db.bills.update_one(
        {"appointment_id": appt["_id"]},
        {"$set": {"payment_mode": mode, "paid_at": _now(), "paid_by": actor["_id"], "paid_by_role": actor["role"]}},
    )
    appt = await appointment_service.set_payment(db, appt, PaymentStatus.PAID)
    return await get_bill(db, appt)


async def waive(db: AsyncDatabase, appt: dict, reason: str, actor: dict) -> dict:
    if appt["payment_status"] != PaymentStatus.UNPAID.value:
        raise Conflict("This bill is already settled")
    await get_bill(db, appt)
    await db.bills.update_one(
        {"appointment_id": appt["_id"]},
        {"$set": {"waive_reason": reason, "paid_at": _now(), "paid_by": actor["_id"], "paid_by_role": actor["role"]}},
    )
    appt = await appointment_service.set_payment(db, appt, PaymentStatus.WAIVED)
    return await get_bill(db, appt)
