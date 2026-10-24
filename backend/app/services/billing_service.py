"""Visit bills: consultation fee from the visit type, extra line items, concessions with approval rules,
GST, split/partial payments, refunds with approval, and auto-numbered receipts.

All arithmetic is in app.billing.calc (integer paise). The appointment's payment_status mirrors the bill,
because a paid visit anchors the follow-up window."""

import secrets
from datetime import date, datetime, time, timezone

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.billing import calc
from app.core import clock
from app.core.clock import clinic_tz
from app.core.errors import Conflict, Forbidden, Invalid, NotFound
from app.schemas.appointment import PaymentStatus
from app.schemas.billing import BillIn, BillingSettings, PaymentIn, RefundIn
from app.schemas.common import parse_object_id
from app.services import audit_service, scheduling_service

VISIT_LABELS = {"new": "New visit", "follow_up": "Follow-up", "returning": "Returning", "emergency": "Emergency / after-hours",
                "teleconsultation": "Teleconsultation"}
CONSULTATION_ID = "consultation"


def _now() -> datetime:
    """Through the clinic clock, so receipts land on the right business day (and tests can fix the time)."""
    now = clock.clinic_now().astimezone(timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


# --- settings --------------------------------------------------------------------


async def get_settings(db: AsyncDatabase) -> dict:
    doc = await db.settings.find_one({"_id": "billing"}) or {}
    return BillingSettings(**{k: v for k, v in doc.items() if k != "_id"}).model_dump()


async def save_settings(db: AsyncDatabase, data: BillingSettings) -> dict:
    await db.settings.update_one({"_id": "billing"}, {"$set": data.model_dump()}, upsert=True)
    return await get_settings(db)


def fee_for(doctor: dict, key: str, settings: dict) -> tuple[int | None, str | None]:
    """Whole rupees for this kind of visit: the doctor's own fee, else the specialty's, else not set."""
    own = (doctor.get("fees") or {}).get(key)
    if own is not None:
        return own, "doctor"
    specialty = (settings["specialty_fees"].get(doctor.get("specialization") or "") or {}).get(key)
    if specialty is not None:
        return specialty, "specialty"
    return None, None


# --- the bill ----------------------------------------------------------------------


def _blank(appt: dict) -> dict:
    return {
        "v": 2,
        "appointment_id": appt["_id"],
        "patient_id": appt["patient_id"],
        "doctor_id": appt["doctor_id"],
        "date": appt["date"],
        "items": [],
        "fee": {"basis": "auto", "amount": None, "reason": None},
        "concession": {"type": "none", "percent": None, "amount": None, "reason": None, "status": "none"},
        "payments": [],
        "refunds": [],
        "cancel": None,
        "created_at": _now(),
    }


def _migrate(old: dict, appt: dict) -> dict:
    """Bills from before fee rules: whole-rupee lines, a flat discount and a single payment."""
    bill = {**_blank(appt), "_id": old["_id"], "created_at": old.get("created_at", _now())}
    for item in old.get("items", []):
        if item.get("id") == CONSULTATION_ID and item.get("auto"):
            continue
        if item.get("id") == CONSULTATION_ID:  # edited consultation line -> custom fee
            bill["fee"] = {"basis": "custom", "amount": item["amount"] * 100, "reason": "Edited before fee rules"}
            continue
        bill["items"].append({"id": item.get("id") or secrets.token_hex(4), "kind": item.get("kind", "other"), "service_id": None,
                              "description": item["description"], "qty": 1, "unit_price": item["amount"] * 100, "tax_rate": 0})
    if old.get("discount"):
        bill["concession"] = {"type": "other", "percent": None, "amount": old["discount"] * 100, "reason": "Discount", "status": "approved"}
    if old.get("waive_reason"):
        bill["concession"] = {"type": "waiver", "percent": 100, "amount": None, "reason": old["waive_reason"], "status": "approved"}
    bill["legacy_paid"] = appt.get("payment_status") == PaymentStatus.PAID.value and old.get("paid_at")
    if bill["legacy_paid"]:
        bill["legacy_payment"] = {"mode": old.get("payment_mode") or "other", "at": old["paid_at"], "by_role": old.get("paid_by_role", "receptionist")}
    return bill


async def _load(db: AsyncDatabase, appt: dict) -> dict:
    bill = await db.bills.find_one({"appointment_id": appt["_id"]})
    if bill is None:
        bill = _blank(appt)
        try:
            bill["_id"] = (await db.bills.insert_one(bill)).inserted_id
        except Exception:  # created concurrently
            bill = await db.bills.find_one({"appointment_id": appt["_id"]})
    elif bill.get("v") != 2:
        migrated = _migrate(bill, appt)
        legacy = migrated.pop("legacy_payment", None)
        migrated.pop("legacy_paid", None)
        await db.bills.replace_one({"_id": bill["_id"]}, migrated)
        bill = migrated
        if legacy:  # record the old payment for the full amount, with a receipt
            doctor = await scheduling_service.get_doctor(db, appt["doctor_id"])
            view = _compute(bill, appt, doctor, await get_settings(db))
            if view["balance"] > 0:
                bill = await _add_payment(db, bill, appt, {"mode": legacy["mode"], "amount": view["balance"], "reference": "migrated"},
                                          {"_id": None, "role": legacy["by_role"]}, at=legacy["at"])
    return bill


def _consultation(bill: dict, appt: dict, doctor: dict, settings: dict) -> tuple[dict, dict, bool]:
    fee = bill["fee"]
    frozen = fee.get("frozen")  # the fee is fixed once the first payment is taken
    if frozen:
        key, amount, source = frozen["key"], frozen["amount"], frozen["source"]
    elif fee["basis"] == "custom":
        key, amount, source = appt["visit_type"], fee["amount"], "custom"
    else:
        key = appt["visit_type"] if fee["basis"] == "auto" else fee["basis"]
        rupee_fee, source = fee_for(doctor, key, settings)
        amount = None if rupee_fee is None else rupee_fee * 100
    missing = amount is None
    line = {
        "id": CONSULTATION_ID,
        "kind": "consultation",
        "service_id": None,
        "description": f"Consultation - {VISIT_LABELS.get(key, key)} ({doctor['full_name']})",
        "qty": 1,
        "unit_price": amount or 0,
        "tax_rate": settings["consultation_tax_rate"],
        "auto": fee["basis"] == "auto" and not frozen,
    }
    info = {"basis": fee["basis"], "key": key, "amount": amount or 0, "source": source, "reason": fee.get("reason")}
    return line, info, missing


def _discount(bill: dict, subtotal: int, settings: dict) -> int:
    c = bill["concession"]
    if c["type"] == "none" or c["status"] != "approved":
        return 0
    if c["type"] == "waiver":
        return subtotal
    if c.get("amount") is not None and c.get("percent") is None:
        return calc.discount_for(subtotal, fixed=c["amount"])
    return calc.discount_for(subtotal, percent_bp=round((c.get("percent") or 0) * 100))


def _compute(bill: dict, appt: dict, doctor: dict, settings: dict) -> dict:
    consult, fee_info, missing = _consultation(bill, appt, doctor, settings)
    lines = [consult, *({**i, "auto": False} for i in bill["items"])]
    calc_lines = [calc.Line(l["qty"], l["unit_price"], calc.rate_bp(l["tax_rate"])) for l in lines]
    subtotal = sum(l.amount for l in calc_lines)
    totals = calc.compute(calc_lines, discount=_discount(bill, subtotal, settings), round_to_rupee=settings["round_to_rupee"])
    paid = sum(p["amount"] for p in bill["payments"])
    refunded = sum(r["amount"] for r in bill["refunds"] if r["status"] == "approved")
    net = paid - refunded
    c = bill["concession"]
    if bill.get("cancel"):
        status = "cancelled"
    elif totals["total"] == 0 and c["type"] == "waiver" and c["status"] == "approved":
        status = "waived"
    elif totals["total"] == 0:
        status = "paid" if bill["payments"] else "unpaid"
    elif net >= totals["total"]:
        status = "paid"
    elif net > 0:
        status = "partial"
    else:
        status = "unpaid"
    return {
        "items": [{**l, **t} for l, t in zip(lines, totals.pop("lines"))],
        "fee": fee_info,
        "fee_missing": missing,
        **totals,
        "paid": paid,
        "refunded": refunded,
        "balance": 0 if status in ("cancelled", "waived") else max(0, totals["total"] - net),
        "status": status,
    }


def _view(bill: dict, appt: dict, computed: dict) -> dict:
    c = bill["concession"]
    return {
        "id": str(bill["_id"]),
        "appointment_id": str(appt["_id"]),
        "patient_id": appt["patient_id"],
        "visit_type": appt["visit_type"],
        **computed,
        "concession": {**c, "discount": computed["discount"]},
        "payments": bill["payments"],
        "refunds": bill["refunds"],
        "cancel_reason": (bill.get("cancel") or {}).get("reason"),
    }


async def _sync(db: AsyncDatabase, bill: dict, appt: dict) -> tuple[dict, dict]:
    """Recompute, store the totals (for dues and reports) and mirror the status onto the appointment."""
    doctor = await scheduling_service.get_doctor(db, appt["doctor_id"])
    computed = _compute(bill, appt, doctor, await get_settings(db))
    await db.bills.update_one(
        {"_id": bill["_id"]},
        {"$set": {"total": computed["total"], "balance": computed["balance"], "status": computed["status"], "updated_at": _now()}},
    )
    payment_status = {"cancelled": "unpaid"}.get(computed["status"], computed["status"])
    if appt.get("payment_status") != payment_status:
        appt = await db.appointments.find_one_and_update(
            {"_id": appt["_id"]}, {"$set": {"payment_status": payment_status}}, return_document=ReturnDocument.AFTER
        )
    return computed, appt


async def get_bill(db: AsyncDatabase, appt: dict) -> dict:
    """The visit's bill, created on first view. While nothing is paid, the consultation line follows the
    detected visit type (and changes to it)."""
    bill = await _load(db, appt)
    computed, appt = await _sync(db, bill, appt)
    return _view(bill, appt, computed)


def _require_open(view: dict) -> None:
    if view["status"] in ("cancelled", "waived"):
        raise Conflict(f"This bill is {view['status']}")


def _needs_approval(concession: dict, settings: dict) -> bool:
    if concession["type"] == "none":
        return False
    if concession["type"] == "waiver":
        return True
    if concession.get("percent") is not None:
        return concession["percent"] > settings["approval_discount_percent"]
    return True  # fixed amounts are judged by an admin (no subtotal context at entry time)


async def save_bill(db: AsyncDatabase, appt: dict, data: BillIn, actor: dict) -> dict:
    """Autosave of the editable parts. Fee overrides need a reason and are audited; concessions above the
    clinic's limit (and all waivers) wait for an admin unless an admin makes them."""
    bill = await _load(db, appt)
    settings = await get_settings(db)
    doctor = await scheduling_service.get_doctor(db, appt["doctor_id"])
    before = _compute(bill, appt, doctor, settings)
    _require_open(before)
    if before["status"] == "paid" and before["total"] > 0:
        raise Conflict("This bill is fully paid. Refund or cancel it to make changes.")

    items = []
    for item in data.items:
        row = item.model_dump()
        if row["kind"] == "consultation":
            raise Invalid("The consultation line comes from the fee choice")
        row["id"] = row["id"] or secrets.token_hex(4)
        items.append(row)

    update: dict = {"items": items}
    fee = data.fee.model_dump()
    old_fee = bill["fee"]
    if (fee["basis"], fee["amount"]) != (old_fee["basis"], old_fee.get("amount")):
        if bill["fee"].get("frozen"):
            raise Conflict("The consultation fee is fixed once a payment has been taken")
        update["fee"] = {**fee, "by_role": actor["role"], "at": _now()}
        if fee["basis"] != "auto":
            await audit_service.record(db, actor=actor, action="fee_override", resource="bills", resource_id=str(bill["_id"]),
                                       patient_id=appt["patient_id"],
                                       details={"from": old_fee["basis"], "to": fee["basis"], "amount": fee["amount"], "reason": fee["reason"]})
    elif fee.get("reason") != old_fee.get("reason"):
        update["fee.reason"] = fee["reason"]

    concession = data.concession.model_dump()
    if concession["type"] in ("senior", "staff") and concession["percent"] is None:
        concession["percent"] = settings[f"{concession['type']}_percent"]
    if concession["type"] == "waiver":
        concession.update(percent=100, amount=None)
    old_c = bill["concession"]
    same = all(concession[k] == old_c.get(k) for k in ("type", "percent", "amount", "reason"))
    if not same:
        if concession["type"] == "none":
            concession["status"] = "none"
        elif _needs_approval(concession, settings) and actor["role"] != "admin":
            concession["status"] = "pending"
        else:
            concession["status"] = "approved"
            concession["approved_by_role"] = actor["role"]
        concession["requested_by_role"] = actor["role"]
        update["concession"] = concession

    candidate = {**bill, **{k: v for k, v in update.items() if "." not in k}}
    after = _compute(candidate, appt, doctor, settings)
    net = after["paid"] - after["refunded"]
    if after["total"] < net:
        raise Invalid("The new total would be less than what has already been paid; refund the difference first")
    await db.bills.update_one({"_id": bill["_id"]}, {"$set": update})
    return await get_bill(db, appt)


async def decide_concession(db: AsyncDatabase, appt: dict, approve: bool, actor: dict) -> dict:
    bill = await _load(db, appt)
    if bill["concession"]["status"] != "pending":
        raise Conflict("No concession is waiting for approval")
    status = "approved" if approve else "rejected"
    await db.bills.update_one({"_id": bill["_id"]}, {"$set": {"concession.status": status, "concession.approved_by_role": actor["role"]}})
    await audit_service.record(db, actor=actor, action="discount_approved" if approve else "discount_rejected", resource="bills",
                               resource_id=str(bill["_id"]), patient_id=appt["patient_id"], details={k: bill["concession"].get(k) for k in ("type", "percent", "amount", "reason")})
    return await get_bill(db, appt)


# --- payments, receipts and refunds -----------------------------------------------


def financial_year(day: date) -> str:
    """Indian financial year, April to March: 2026-10-24 -> '2026-27'."""
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


async def _next_number(db: AsyncDatabase, prefix: str) -> str:
    fy = financial_year(clock.clinic_now().date())
    counter = await db.counters.find_one_and_update(
        {"_id": f"{prefix}:{fy}"}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return f"{prefix}/{fy}/{counter['seq']:06d}"


async def next_appointment(db: AsyncDatabase, appt: dict) -> dict | None:
    """The booked follow-up with this doctor, else the date the doctor advised on the prescription."""
    booked = await db.appointments.find_one(
        {"patient_id": appt["patient_id"], "doctor_id": appt["doctor_id"], "date": {"$gt": appt["date"]}, "status": "scheduled"},
        sort=[("date", 1), ("start_time", 1)],
    )
    if booked:
        return {"date": booked["date"], "time": booked.get("start_time"), "booked": True, "appointment_id": str(booked["_id"])}
    rx = await db.prescriptions.find_one({"appointment_id": appt["_id"]}, {"follow_up": 1})
    follow = (rx or {}).get("follow_up") or {}
    if follow.get("date"):
        return {"date": str(follow["date"])[:10], "time": None, "booked": False, "note": follow.get("note")}
    return None


async def _issue_receipt(db: AsyncDatabase, bill: dict, appt: dict, *, kind: str, entry: dict, actor: dict, at: datetime) -> dict:
    from app.services import prescription_service, patient_service  # avoid import cycles

    doctor = await scheduling_service.get_doctor(db, appt["doctor_id"])
    computed = _compute(bill, appt, doctor, await get_settings(db))
    patient = await patient_service.get_patient(db, appt["patient_id"])
    receipt = {
        "number": await _next_number(db, "RCP" if kind == "payment" else "RFD"),
        "kind": kind,
        "bill_id": bill["_id"],
        "appointment_id": appt["_id"],
        "patient_id": appt["patient_id"],
        "entry_id": entry["id"],
        "amount": entry["amount"],
        "mode": entry["mode"],
        "reference": entry.get("reference"),
        "reason": entry.get("reason"),
        "issued_at": at,
        "issued_by": actor.get("_id"),
        "issued_by_role": actor["role"],
        "total": computed["total"],
        "balance": computed["balance"],
        "next_appointment": await next_appointment(db, appt),
        "snapshot": {
            "clinic": await prescription_service.clinic_settings(db),
            "patient": {"patient_id": patient["patient_id"], "name": patient["full_name"], "phone": patient.get("phone"),
                        "gender": patient.get("gender"), "date_of_birth": patient.get("date_of_birth")},
            "doctor": {"name": doctor["full_name"], "specialization": doctor.get("specialization"), "registration_number": doctor.get("registration_number")},
            "visit": {"date": appt["date"], "visit_type": computed["fee"]["key"], "token": appt.get("token")},
            "bill": {k: computed[k] for k in ("items", "subtotal", "discount", "taxable", "tax_by_rate", "tax", "round_off", "total", "paid", "refunded", "balance", "status")},
            "concession": {k: bill["concession"].get(k) for k in ("type", "percent", "amount", "reason", "status")},
            "payments": [{k: p.get(k) for k in ("mode", "amount", "reference", "at", "receipt_number")} for p in bill["payments"]],
        },
    }
    receipt["_id"] = (await db.receipts.insert_one(receipt)).inserted_id
    return receipt


async def _add_payment(db: AsyncDatabase, bill: dict, appt: dict, data: dict, actor: dict, at: datetime | None = None) -> dict:
    at = at or _now()
    payment = {"id": secrets.token_hex(4), "mode": data["mode"], "amount": data["amount"], "reference": data.get("reference"),
               "at": at, "by": actor.get("_id"), "by_role": actor["role"], "receipt_id": None, "receipt_number": None}
    set_fee: dict = {}
    if not bill["fee"].get("frozen"):  # fix the fee: later visit-type changes no longer reprice a paid visit
        doctor = await scheduling_service.get_doctor(db, appt["doctor_id"])
        _, info, _ = _consultation(bill, appt, doctor, await get_settings(db))
        set_fee = {"fee.frozen": {"key": info["key"], "amount": info["amount"], "source": info["source"]}}
    bill = await db.bills.find_one_and_update(
        {"_id": bill["_id"]}, {"$push": {"payments": payment}, "$set": set_fee} if set_fee else {"$push": {"payments": payment}},
        return_document=ReturnDocument.AFTER,
    )
    receipt = await _issue_receipt(db, bill, appt, kind="payment", entry=payment, actor=actor, at=at)
    return await db.bills.find_one_and_update(
        {"_id": bill["_id"], "payments.id": payment["id"]},
        {"$set": {"payments.$.receipt_id": str(receipt["_id"]), "payments.$.receipt_number": receipt["number"]}},
        return_document=ReturnDocument.AFTER,
    )


async def pay(db: AsyncDatabase, appt: dict, data: PaymentIn, actor: dict) -> tuple[dict, dict]:
    """Record a payment (several can make up a split or partial payment) and issue its receipt."""
    view = await get_bill(db, appt)
    _require_open(view)
    if view["concession"]["status"] == "pending":
        raise Conflict("A concession is waiting for an admin's approval")
    if view["fee_missing"]:
        raise Invalid("No consultation fee is set for this kind of visit. Set the doctor's fees or choose a fee.")
    if view["total"] == 0:
        if view["payments"]:
            raise Conflict("Already settled")
        if data.amount != 0:
            raise Invalid("Nothing is due on this bill")
    elif data.amount <= 0:
        raise Invalid("Enter the amount received")
    elif data.amount > view["balance"]:
        raise Invalid(f"Only ₹{calc.rupees(view['balance'])} is due")
    bill = await _add_payment(db, await _load(db, appt), appt, data.model_dump(), actor)
    computed, appt = await _sync(db, bill, appt)
    receipt = await db.receipts.find_one({"bill_id": bill["_id"], "entry_id": bill["payments"][-1]["id"]})
    return _view(bill, appt, computed), receipt


async def request_refund(db: AsyncDatabase, appt: dict, data: RefundIn, actor: dict) -> dict:
    view = await get_bill(db, appt)
    pending = sum(r["amount"] for r in view["refunds"] if r["status"] == "requested")
    if data.amount > view["paid"] - view["refunded"] - pending:
        raise Invalid("That is more than was paid on this bill")
    refund = {"id": secrets.token_hex(4), "amount": data.amount, "mode": data.mode, "reason": data.reason, "status": "requested",
              "requested_at": _now(), "requested_by": actor["_id"], "requested_by_role": actor["role"],
              "decided_at": None, "decided_by_role": None, "receipt_number": None}
    bill = await _load(db, appt)
    await db.bills.update_one({"_id": bill["_id"]}, {"$push": {"refunds": refund}})
    if actor["role"] == "admin":
        return await decide_refund(db, appt, refund["id"], True, actor)
    return await get_bill(db, appt)


async def decide_refund(db: AsyncDatabase, appt: dict, refund_id: str, approve: bool, actor: dict) -> dict:
    if actor["role"] != "admin":
        raise Forbidden("Only an admin can approve refunds")
    bill = await _load(db, appt)
    refund = next((r for r in bill["refunds"] if r["id"] == refund_id), None)
    if not refund or refund["status"] != "requested":
        raise NotFound("No refund request to decide")
    status = "approved" if approve else "rejected"
    bill = await db.bills.find_one_and_update(
        {"_id": bill["_id"], "refunds.id": refund_id},
        {"$set": {"refunds.$.status": status, "refunds.$.decided_at": _now(), "refunds.$.decided_by": actor["_id"], "refunds.$.decided_by_role": actor["role"]}},
        return_document=ReturnDocument.AFTER,
    )
    if approve:
        receipt = await _issue_receipt(db, bill, appt, kind="refund", entry=refund, actor=actor, at=_now())
        await db.bills.update_one({"_id": bill["_id"], "refunds.id": refund_id}, {"$set": {"refunds.$.receipt_number": receipt["number"]}})
    await audit_service.record(db, actor=actor, action="refund" if approve else "refund_rejected", resource="bills", resource_id=str(bill["_id"]),
                               patient_id=appt["patient_id"], details={"amount": refund["amount"], "mode": refund["mode"], "reason": refund["reason"]})
    return await get_bill(db, appt)


async def cancel(db: AsyncDatabase, appt: dict, reason: str, actor: dict) -> dict:
    view = await get_bill(db, appt)
    if view["paid"] - view["refunded"] > 0:
        raise Conflict("Refund the payments before cancelling the bill")
    bill = await _load(db, appt)
    await db.bills.update_one({"_id": bill["_id"]}, {"$set": {"cancel": {"reason": reason, "by": actor["_id"], "by_role": actor["role"], "at": _now()}}})
    await audit_service.record(db, actor=actor, action="bill_cancelled", resource="bills", resource_id=str(bill["_id"]), patient_id=appt["patient_id"], details={"reason": reason})
    return await get_bill(db, appt)


# --- receipts -----------------------------------------------------------------------


async def receipts_for(db: AsyncDatabase, appt: dict) -> list[dict]:
    return await db.receipts.find({"appointment_id": appt["_id"]}).sort("issued_at", 1).to_list(100)


async def get_receipt(db: AsyncDatabase, receipt_id: str) -> dict:
    oid = parse_object_id(receipt_id)
    receipt = oid and await db.receipts.find_one({"_id": oid})
    if not receipt:
        raise NotFound("Receipt not found")
    return receipt


# --- reports ---------------------------------------------------------------------------


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    tz = clinic_tz()
    return (datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc), datetime.combine(day, time.max, tzinfo=tz).astimezone(timezone.utc))


async def collections(db: AsyncDatabase, day: date) -> dict:
    """The day's money in and out, from the receipts ledger (so it always equals the sum of receipts)."""
    start, end = _day_bounds(day)
    receipts = await db.receipts.find({"issued_at": {"$gte": start, "$lte": end}}).sort("issued_at", 1).to_list(None)
    by_mode: dict[str, dict] = {}
    by_staff: dict[str, int] = {}
    for r in receipts:
        sign = 1 if r["kind"] == "payment" else -1
        m = by_mode.setdefault(r["mode"], {"mode": r["mode"], "received": 0, "refunded": 0, "net": 0})
        m["received" if sign > 0 else "refunded"] += r["amount"]
        m["net"] += sign * r["amount"]
        by_staff[r["issued_by_role"]] = by_staff.get(r["issued_by_role"], 0) + sign * r["amount"]
    received = sum(r["amount"] for r in receipts if r["kind"] == "payment")
    refunded = sum(r["amount"] for r in receipts if r["kind"] == "refund")
    recon = await db.reconciliations.find_one({"date": day.isoformat()}, sort=[("at", -1)])
    return {
        "date": day.isoformat(),
        "received": received,
        "refunded": refunded,
        "net": received - refunded,
        "receipt_count": len(receipts),
        "by_mode": sorted(by_mode.values(), key=lambda m: m["mode"]),
        "by_role": [{"role": k, "net": v} for k, v in sorted(by_staff.items())],
        "receipts": receipts,
        "reconciliation": recon,
    }


async def reconcile(db: AsyncDatabase, day: date, counted: dict, note: str | None, actor: dict) -> dict:
    """End of day: what was counted (cash in the drawer, UPI/card settlement) against what the receipts say."""
    report = await collections(db, day)
    expected = {m["mode"]: m["net"] for m in report["by_mode"]}
    modes = sorted(set(expected) | set(counted))
    rows = [{"mode": m, "expected": expected.get(m, 0), "counted": counted.get(m, 0), "variance": counted.get(m, 0) - expected.get(m, 0)} for m in modes]
    doc = {"date": day.isoformat(), "rows": rows, "variance": sum(r["variance"] for r in rows), "note": note,
           "by": actor["_id"], "by_role": actor["role"], "at": _now()}
    doc["_id"] = (await db.reconciliations.insert_one(doc)).inserted_id
    await audit_service.record(db, actor=actor, action="reconciliation", resource="billing", resource_id=day.isoformat(), details={"variance": doc["variance"]})
    return doc


async def receipts_csv(db: AsyncDatabase, date_from: date, date_to: date) -> str:
    import csv
    import io

    start, _ = _day_bounds(date_from)
    _, end = _day_bounds(date_to)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["number", "kind", "issued_at", "patient_id", "patient_name", "doctor", "visit_date", "visit_type", "mode", "reference",
                "amount", "bill_total", "taxable", "cgst", "sgst", "balance_after"])
    async for r in db.receipts.find({"issued_at": {"$gte": start, "$lte": end}}).sort("issued_at", 1):
        snap = r["snapshot"]
        tax = snap["bill"]["tax_by_rate"]
        sign = 1 if r["kind"] == "payment" else -1
        w.writerow([r["number"], r["kind"], r["issued_at"].astimezone(clinic_tz()).isoformat(timespec="seconds"), r["patient_id"], snap["patient"]["name"],
                    snap["doctor"]["name"], snap["visit"]["date"], snap["visit"]["visit_type"], r["mode"], r.get("reference") or "",
                    calc.rupees(sign * r["amount"]), calc.rupees(snap["bill"]["total"]), calc.rupees(snap["bill"]["taxable"]),
                    calc.rupees(sum(t["cgst"] for t in tax)), calc.rupees(sum(t["sgst"] for t in tax)), calc.rupees(r["balance"])])
    return out.getvalue()


async def dues(db: AsyncDatabase) -> list[dict]:
    """Bills with money outstanding: part-paid, or unpaid after the visit was completed."""
    bills = await db.bills.find({"v": 2, "balance": {"$gt": 0}, "status": {"$in": ["unpaid", "partial"]}}).sort("date", -1).to_list(500)
    appts = {a["_id"]: a for a in await db.appointments.find({"_id": {"$in": [b["appointment_id"] for b in bills]}}).to_list(None)}
    patients = {p["patient_id"]: p for p in await db.patients.find({"patient_id": {"$in": [b["patient_id"] for b in bills]}}, {"patient_id": 1, "full_name": 1, "phone": 1}).to_list(None)}
    out = []
    for b in bills:
        a = appts.get(b["appointment_id"])
        if not a or (b["status"] == "unpaid" and a["status"] != "completed"):
            continue
        p = patients.get(b["patient_id"], {})
        out.append({"appointment_id": str(a["_id"]), "patient_id": b["patient_id"], "patient_name": p.get("full_name"), "phone": p.get("phone"),
                    "date": b["date"], "doctor_name": a.get("doctor_name"), "total": b["total"], "balance": b["balance"], "status": b["status"]})
    return out


async def pending_approvals(db: AsyncDatabase) -> dict:
    """Concessions and refunds waiting for an admin."""
    concessions, refunds = [], []
    async for b in db.bills.find({"v": 2, "$or": [{"concession.status": "pending"}, {"refunds.status": "requested"}]}):
        base = {"appointment_id": str(b["appointment_id"]), "patient_id": b["patient_id"], "date": b["date"]}
        if b["concession"]["status"] == "pending":
            concessions.append({**base, **{k: b["concession"].get(k) for k in ("type", "percent", "amount", "reason", "requested_by_role")}})
        refunds += [{**base, **{k: r[k] for k in ("id", "amount", "mode", "reason", "requested_by_role", "requested_at")}} for r in b["refunds"] if r["status"] == "requested"]
    return {"concessions": concessions, "refunds": refunds}


async def patient_bills(db: AsyncDatabase, patient_id: str) -> list[dict]:
    """For the patient app: each visit's total, balance and receipts."""
    out = []
    async for b in db.bills.find({"v": 2, "patient_id": patient_id}).sort("date", -1).limit(100):
        appt = await db.appointments.find_one({"_id": b["appointment_id"]})
        if not appt:
            continue
        view = await get_bill(db, appt)
        receipts = await db.receipts.find({"bill_id": b["_id"]}, {"number": 1, "kind": 1, "amount": 1, "mode": 1, "issued_at": 1}).sort("issued_at", 1).to_list(None)
        out.append({"appointment_id": str(appt["_id"]), "date": appt["date"], "doctor_name": appt.get("doctor_name"), "visit_type": appt["visit_type"],
                    "total": view["total"], "paid": view["paid"] - view["refunded"], "balance": view["balance"], "status": view["status"],
                    "receipts": [{**{k: v for k, v in r.items() if k != "_id"}, "id": str(r["_id"])} for r in receipts]})
    return out



# --- receipt delivery -------------------------------------------------------------


def receipt_pdf(receipt: dict, fmt: str = "a5") -> bytes:
    from app.billing import receipt_pdf as pdf

    return pdf.render(receipt, fmt)


async def receipt_link(db: AsyncDatabase, receipt: dict) -> str:
    from app.core.config import settings
    from app.services import messaging

    token = await messaging.issue_link_token(db, "receipt", receipt["_id"])
    return f"{settings.api_public_url.rstrip('/')}{settings.api_prefix}/public/receipts/{receipt['_id']}/pdf?token={token}"


async def deliver_receipt(db: AsyncDatabase, receipt: dict, *, channel: str, to: str | None, actor: dict) -> dict:
    """Print / WhatsApp / SMS / email / patient app, like prescriptions."""
    import asyncio
    import logging

    from app.services import messaging, patient_service

    patient = await patient_service.get_patient(db, receipt["patient_id"])
    clinic = receipt["snapshot"]["clinic"]["name"]
    record = {"receipt_id": receipt["_id"], "appointment_id": receipt["appointment_id"], "channel": channel, "to": None, "link": None,
              "share_url": None, "detail": None, "at": _now(), "by": actor["_id"], "by_role": actor["role"]}
    if channel == "print":
        record.update(status="recorded", detail="Printed / downloaded")
    elif channel == "patient_app":
        record.update(status="published" if patient.get("managed_by") else "failed",
                      detail="In the patient's app (Bills)" if patient.get("managed_by") else "This patient has no app account")
    else:
        link = await receipt_link(db, receipt)
        what = "refund receipt" if receipt["kind"] == "refund" else "receipt"
        message = f"{clinic}: your {what} {receipt['number']} for Rs {calc.rupees(receipt['amount'])}. Balance due: Rs {calc.rupees(receipt['balance'])}. {link}"
        record["link"] = link
        if channel in ("whatsapp", "sms"):
            phone = to or patient["phone"]
            record.update(to=phone, status="link_ready", detail="Opens on this device to send",
                          share_url=messaging.whatsapp_url(phone, message) if channel == "whatsapp" else messaging.sms_url(phone, message))
        else:
            email = to or patient.get("email")
            if not email:
                raise Invalid("No email address for this patient")
            record["to"] = email
            if messaging.smtp_configured():
                try:
                    await asyncio.to_thread(messaging.smtp_send, email, f"Receipt {receipt['number']} - {clinic}", message,
                                            [(receipt_pdf(receipt), receipt["number"].replace("/", "-") + ".pdf")])
                    record.update(status="sent", detail="Emailed with the PDF attached")
                except Exception as exc:  # SMTP errors vary widely
                    logging.getLogger(__name__).warning("Receipt email failed: %s", exc)
                    record.update(status="failed", detail="Email could not be sent; try again or share the link")
            else:
                record.update(status="link_ready", detail="Email server not configured: opens your mail app with the link",
                              share_url=messaging.mailto_url(email, f"Receipt {receipt['number']} - {clinic}", message))
    await db.receipt_deliveries.insert_one(record)
    return record
