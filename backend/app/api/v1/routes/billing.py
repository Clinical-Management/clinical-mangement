from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.core.clock import clinic_today
from app.core.deps import DB, CurrentUser, require_roles
from app.core.errors import Forbidden, Invalid, NotFound
from app.schemas.billing import (
    BillIn,
    BillingSettings,
    BillOut,
    PaymentIn,
    ReasonIn,
    ReceiptDeliveryIn,
    ReceiptOut,
    ReconciliationIn,
    RefundIn,
    ServiceIn,
    ServiceOut,
)
from app.schemas.common import parse_object_id
from app.schemas.user import Role
from app.services import appointment_service, billing_service as svc, messaging, report_service

router = APIRouter(tags=["billing"])

Billing = Depends(require_roles(Role.ADMIN, Role.RECEPTIONIST, Role.DOCTOR))
FrontDesk = Depends(require_roles(Role.ADMIN, Role.RECEPTIONIST))
Admin = Depends(require_roles(Role.ADMIN))


async def visit(appointment_id: str, db: DB, user: CurrentUser) -> dict:
    return await appointment_service.get_for_user(db, appointment_id, user)


Visit = Annotated[dict, Depends(visit)]


async def receipt_for(receipt_id: str, db: DB, user: CurrentUser) -> dict:
    receipt = await svc.get_receipt(db, receipt_id)
    await appointment_service.get_for_user(db, str(receipt["appointment_id"]), user)  # same access as the visit
    return receipt


Receipt = Annotated[dict, Depends(receipt_for)]


def _receipt_view(r: dict) -> dict:
    return {**r, "id": str(r["_id"])}


# --- the visit's bill ---------------------------------------------------------------


@router.get("/appointments/{appointment_id}/bill", response_model=BillOut, dependencies=[Billing])
async def get_bill(appt: Visit, db: DB):
    """Charges for this visit; the consultation line is priced from the detected visit type."""
    return await svc.get_bill(db, appt)


@router.put("/appointments/{appointment_id}/bill", response_model=BillOut, dependencies=[Billing])
async def save_bill(body: BillIn, appt: Visit, db: DB, user: CurrentUser):
    """Line items, fee choice (overrides need a reason and are audited) and concession."""
    return await svc.save_bill(db, appt, body, user)


@router.post("/appointments/{appointment_id}/bill/payments", dependencies=[FrontDesk])
async def take_payment(body: PaymentIn, appt: Visit, db: DB, user: CurrentUser):
    """One payment (record several for split or partial payment). Returns the bill and the new receipt."""
    bill, receipt = await svc.pay(db, appt, body, user)
    return {"bill": BillOut(**bill), "receipt": ReceiptOut.model_validate(receipt)}


@router.post("/appointments/{appointment_id}/bill/concession/{decision}", response_model=BillOut, dependencies=[Admin])
async def decide_concession(decision: Literal["approve", "reject"], appt: Visit, db: DB, user: CurrentUser):
    return await svc.decide_concession(db, appt, decision == "approve", user)


@router.post("/appointments/{appointment_id}/bill/refunds", response_model=BillOut, dependencies=[FrontDesk])
async def request_refund(body: RefundIn, appt: Visit, db: DB, user: CurrentUser):
    """Front desk requests; an admin approves (an admin's own refund is approved at once)."""
    return await svc.request_refund(db, appt, body, user)


@router.post("/appointments/{appointment_id}/bill/refunds/{refund_id}/{decision}", response_model=BillOut, dependencies=[Admin])
async def decide_refund(refund_id: str, decision: Literal["approve", "reject"], appt: Visit, db: DB, user: CurrentUser):
    return await svc.decide_refund(db, appt, refund_id, decision == "approve", user)


@router.post("/appointments/{appointment_id}/bill/cancel", response_model=BillOut, dependencies=[Admin])
async def cancel_bill(body: ReasonIn, appt: Visit, db: DB, user: CurrentUser):
    return await svc.cancel(db, appt, body.reason, user)


@router.get("/appointments/{appointment_id}/receipts", response_model=list[ReceiptOut])
async def visit_receipts(appt: Visit, db: DB):
    """Patients see their own; staff see any."""
    return await svc.receipts_for(db, appt)


# --- receipts -------------------------------------------------------------------------


@router.get("/receipts/{receipt_id}/pdf")
async def receipt_pdf(receipt: Receipt, fmt: Literal["a5", "thermal"] = "a5", download: bool = False):
    name = receipt["number"].replace("/", "-") + (".thermal" if fmt == "thermal" else "") + ".pdf"
    disposition = "attachment" if download else "inline"
    return Response(svc.receipt_pdf(receipt, fmt), media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="{name}"'})


@router.post("/receipts/{receipt_id}/deliver", dependencies=[FrontDesk])
async def deliver_receipt(body: ReceiptDeliveryIn, receipt: Receipt, db: DB, user: CurrentUser):
    record = await svc.deliver_receipt(db, receipt, channel=body.channel, to=body.to, actor=user)
    return {k: v for k, v in record.items() if k not in ("_id", "receipt_id", "appointment_id", "by")}


@router.get("/public/receipts/{receipt_id}/pdf")
async def public_receipt(receipt_id: str, db: DB, token: str = Query(min_length=10)):
    """From the WhatsApp / SMS / email link (no login)."""
    oid = parse_object_id(receipt_id)
    if not oid:
        raise NotFound("Receipt not found")
    await messaging.check_link_token(db, "receipt", oid, token)
    receipt = await svc.get_receipt(db, receipt_id)
    name = receipt["number"].replace("/", "-") + ".pdf"
    return Response(svc.receipt_pdf(receipt), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})


@router.get("/patients/{patient_id}/bills")
async def patient_bills(patient_id: str, db: DB, user: CurrentUser):
    """Bills, receipts and dues for one patient (the patient app, or staff)."""
    if user["role"] == Role.DOCTOR.value:
        raise Forbidden("Billing history is for the front desk and the patient")
    patient = await report_service.patient_for(db, patient_id, user)
    return await svc.patient_bills(db, patient["patient_id"])


# --- front desk reports -----------------------------------------------------------------


@router.get("/billing/collections", dependencies=[FrontDesk])
async def collections(db: DB, day: date | None = Query(None, alias="date")):
    """Daily collection: received, refunded and net by payment mode; equals the sum of the day's receipts."""
    report = await svc.collections(db, day or clinic_today())
    report["receipts"] = [ReceiptOut.model_validate(r).model_dump(mode="json") for r in report["receipts"]]
    if report["reconciliation"]:
        report["reconciliation"] = {**report["reconciliation"], "_id": str(report["reconciliation"]["_id"]), "by": str(report["reconciliation"]["by"])}
    return report


@router.post("/billing/reconciliations", dependencies=[FrontDesk])
async def reconcile(body: ReconciliationIn, db: DB, user: CurrentUser):
    """End-of-day: counted cash and settlements against the receipts."""
    doc = await svc.reconcile(db, body.date, body.counted, body.note, user)
    return {**doc, "_id": str(doc["_id"]), "by": str(doc["by"])}


@router.get("/billing/export", dependencies=[FrontDesk])
async def export_receipts(db: DB, date_from: date, date_to: date):
    """Receipts as CSV for the accountant (Tally / Zoho / Excel)."""
    if date_to < date_from or (date_to - date_from).days > 366:
        raise Invalid("Choose a range of up to a year")
    data = await svc.receipts_csv(db, date_from, date_to)
    return Response(data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="receipts-{date_from}-to-{date_to}.csv"'})


@router.get("/billing/dues", dependencies=[FrontDesk])
async def outstanding_dues(db: DB):
    return await svc.dues(db)


@router.get("/billing/approvals", dependencies=[FrontDesk])
async def approvals(db: DB):
    """Concessions and refunds waiting for an admin."""
    return await svc.pending_approvals(db)


# --- settings and price list ---------------------------------------------------------------


@router.get("/billing/settings", response_model=BillingSettings, dependencies=[Billing])
async def get_settings(db: DB):
    return await svc.get_settings(db)


@router.put("/billing/settings", response_model=BillingSettings, dependencies=[Admin])
async def save_settings(body: BillingSettings, db: DB):
    return await svc.save_settings(db, body)


@router.get("/billing/services", response_model=list[ServiceOut], dependencies=[Billing])
async def list_services(db: DB, all: bool = False):
    query = {} if all else {"active": True}
    return await db.services.find(query).sort("name", 1).to_list(500)


@router.post("/billing/services", response_model=ServiceOut, status_code=201, dependencies=[Admin])
async def add_service(body: ServiceIn, db: DB):
    doc = body.model_dump()
    doc["_id"] = (await db.services.insert_one(doc)).inserted_id
    return doc


@router.put("/billing/services/{service_id}", response_model=ServiceOut, dependencies=[Admin])
async def update_service(service_id: str, body: ServiceIn, db: DB):
    oid = parse_object_id(service_id)
    doc = oid and await db.services.find_one_and_update({"_id": oid}, {"$set": body.model_dump()}, return_document=True)
    if not doc:
        raise NotFound("Service not found")
    return doc
