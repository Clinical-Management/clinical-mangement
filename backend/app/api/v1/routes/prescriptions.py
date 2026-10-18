from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from gridfs import AsyncGridFSBucket
from pymongo import ReturnDocument

from app.core.deps import DB, CurrentUser, require_roles
from app.core.errors import Forbidden, Invalid, NotFound
from app.prescribing import medicines as med
from app.prescribing.medicines import CLASS_LABELS
from app.schemas.common import parse_object_id
from app.schemas.prescription import (
    DeliveryIn,
    DeliveryOut,
    FavouriteIn,
    FavouriteOut,
    FinalizeIn,
    MedicineEntry,
    MedicineOut,
    PrescriptionIn,
    PrescriptionOut,
    TemplateIn,
    TemplateOut,
    VersionOut,
)
from app.schemas.settings import ClinicSettings, DoctorCredentials
from app.schemas.user import Role
from app.services import appointment_service, prescription_service as svc, scheduling_service

router = APIRouter(tags=["prescriptions"])

Clinical = Depends(require_roles(Role.ADMIN, Role.DOCTOR))
Admin = Depends(require_roles(Role.ADMIN))
# front desk prints and sends finalized prescriptions
Delivery = Depends(require_roles(Role.ADMIN, Role.DOCTOR, Role.RECEPTIONIST))


async def visit(appointment_id: str, db: DB, user: CurrentUser) -> dict:
    return await appointment_service.get_for_user(db, appointment_id, user)


Visit = Annotated[dict, Depends(visit)]


async def version_for(version_id: str, db: DB, user: CurrentUser) -> dict:
    v = await svc.get_version(db, version_id)
    await appointment_service.get_for_user(db, str(v["appointment_id"]), user)  # same access as the visit
    return v


Version = Annotated[dict, Depends(version_for)]


def _pdf(data: bytes, name: str, download: bool) -> Response:
    disposition = "attachment" if download else "inline"
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="{name}"'})


# --- prescription ------------------------------------------------------------


@router.get("/appointments/{appointment_id}/prescription", response_model=PrescriptionOut, dependencies=[Clinical])
async def get_prescription(appt: Visit, db: DB):
    """The working draft (or the finalized content) with live safety checks."""
    return await svc.get(db, appt)


@router.put("/appointments/{appointment_id}/prescription", response_model=PrescriptionOut, dependencies=[Clinical])
async def save_prescription(body: PrescriptionIn, appt: Visit, db: DB, user: CurrentUser):
    """Autosave. Editing a finalized prescription starts the next version's draft."""
    return await svc.save(db, appt, body, user)


@router.post("/appointments/{appointment_id}/prescription/finalize", response_model=VersionOut, dependencies=[Clinical])
async def finalize(body: FinalizeIn, appt: Visit, db: DB, user: CurrentUser):
    """Runs the safety checks: warnings must be acknowledged (high ones with a reason). Creates a signed,
    immutable version with a verification QR."""
    return svc.version_view(await svc.finalize(db, appt, body, user))


@router.get("/appointments/{appointment_id}/prescription/versions", response_model=list[VersionOut])
async def versions(appt: Visit, db: DB):
    """All finalized versions, newest first (patients see their own; earlier versions stay viewable)."""
    return await svc.list_versions(db, appt)


@router.get("/appointments/{appointment_id}/prescription/deliveries", response_model=list[DeliveryOut], dependencies=[Delivery])
async def delivery_log(appt: Visit, db: DB):
    return await svc.deliveries(db, appt)


@router.get("/prescription-versions/{version_id}/pdf")
async def version_pdf(
    v: Version, db: DB, lang: Literal["en", "hi", "mr"] = "en", copy: Literal["clinic", "patient"] = "clinic", download: bool = False
):
    """Letterhead PDF with case summary, registration number, signature and verification QR.
    The patient copy can be in English, Hindi or Marathi."""
    data = await svc.render_pdf(db, v, lang=lang, copy=copy)
    return _pdf(data, f"{v['public_id']}-v{v['version']}-{copy}-{lang}.pdf", download)


@router.post("/prescription-versions/{version_id}/deliver", response_model=DeliveryOut, dependencies=[Delivery])
async def deliver(body: DeliveryIn, v: Version, db: DB, user: CurrentUser):
    return await svc.deliver(db, v, channel=body.channel, to=body.to, lang=body.language, actor=user)


# --- public: verification QR and patient links (no login) ---------------------


@router.get("/public/prescriptions/{public_id}")
async def verify(public_id: str, db: DB):
    """Scanned from the QR code: is this prescription genuine and current?"""
    return await svc.verify_public(db, public_id)


@router.get("/public/prescriptions/{public_id}/patient", response_model=VersionOut)
async def patient_link(public_id: str, db: DB, token: str = Query(min_length=10)):
    """The prescription behind a WhatsApp/SMS/email link."""
    return svc.version_view(await svc.version_for_link(db, public_id, token))


@router.get("/public/prescriptions/{public_id}/pdf")
async def patient_link_pdf(public_id: str, db: DB, token: str = Query(min_length=10), lang: Literal["en", "hi", "mr"] = "en"):
    v = await svc.version_for_link(db, public_id, token)
    return _pdf(await svc.render_pdf(db, v, lang=lang, copy="patient"), f"{v['public_id']}-{lang}.pdf", False)


# --- medicine search & master ------------------------------------------------


def medicine_out(m: dict) -> dict:
    return {**m, "class_label": CLASS_LABELS.get(m["class"], m["class"].replace("_", " ").capitalize())}


@router.get("/medicines", response_model=list[MedicineOut], dependencies=[Clinical])
async def search_medicines(db: DB, q: str = Query(min_length=1, max_length=60)):
    """Search by generic or brand name."""
    return [medicine_out(m) for m in await med.search(db, q)]


@router.post("/medicines", response_model=MedicineOut, status_code=201, dependencies=[Admin])
async def add_medicine(body: MedicineEntry, db: DB):
    """Add a clinic-specific medicine (or brand) to the master list."""
    await med.ensure_seeded(db)
    doc = {**body.model_dump(by_alias=True), "source": "custom", "active": True, "created_at": datetime.now(timezone.utc)}
    doc["search"] = med.norm(" ".join([doc["generic"], *doc["brands"]]))
    await db.medicines.insert_one(doc)
    return medicine_out(doc)


@router.put("/medicines/{medicine_id}", response_model=MedicineOut, dependencies=[Admin])
async def update_medicine(medicine_id: str, body: MedicineEntry, db: DB):
    """Edit an entry, e.g. to correct a dose limit for your formulary."""
    oid = parse_object_id(medicine_id)
    fields = body.model_dump(by_alias=True)
    fields["search"] = med.norm(" ".join([fields["generic"], *fields["brands"]]))
    doc = oid and await db.medicines.find_one_and_update({"_id": oid}, {"$set": fields}, return_document=ReturnDocument.AFTER)
    if not doc:
        raise NotFound("Medicine not found")
    return medicine_out(doc)


# --- templates & favourites (per doctor) -------------------------------------


@router.get("/prescription-templates", response_model=list[TemplateOut], dependencies=[Clinical])
async def list_templates(db: DB, user: CurrentUser):
    return await db.rx_templates.find({"doctor_id": user["_id"]}).sort("name", 1).to_list(200)


@router.post("/prescription-templates", response_model=TemplateOut, status_code=201, dependencies=[Clinical])
async def save_template(body: TemplateIn, db: DB, user: CurrentUser):
    """Save the current prescription as a named template (e.g. "Viral fever - adult")."""
    doc = {**body.model_dump(mode="json"), "doctor_id": user["_id"], "created_at": datetime.now(timezone.utc)}
    await db.rx_templates.insert_one(doc)
    return doc


@router.delete("/prescription-templates/{template_id}", status_code=204, dependencies=[Clinical])
async def delete_template(template_id: str, db: DB, user: CurrentUser):
    result = await db.rx_templates.delete_one({"_id": parse_object_id(template_id), "doctor_id": user["_id"]})
    if not result.deleted_count:
        raise NotFound("Template not found")


@router.get("/prescription-favourites", response_model=list[FavouriteOut], dependencies=[Clinical])
async def list_favourites(db: DB, user: CurrentUser):
    return await db.rx_favourites.find({"doctor_id": user["_id"]}).sort("medicine.name", 1).to_list(200)


@router.post("/prescription-favourites", response_model=FavouriteOut, status_code=201, dependencies=[Clinical])
async def add_favourite(body: FavouriteIn, db: DB, user: CurrentUser):
    """A medicine with the doctor's usual dose, frequency, duration and instructions."""
    doc = {"medicine": body.medicine.model_dump(mode="json"), "doctor_id": user["_id"]}
    await db.rx_favourites.replace_one({"doctor_id": user["_id"], "medicine.name": doc["medicine"]["name"]}, doc, upsert=True)
    return await db.rx_favourites.find_one({"doctor_id": user["_id"], "medicine.name": doc["medicine"]["name"]})


@router.delete("/prescription-favourites/{favourite_id}", status_code=204, dependencies=[Clinical])
async def delete_favourite(favourite_id: str, db: DB, user: CurrentUser):
    result = await db.rx_favourites.delete_one({"_id": parse_object_id(favourite_id), "doctor_id": user["_id"]})
    if not result.deleted_count:
        raise NotFound("Favourite not found")


# --- letterhead: clinic settings, doctor registration & signature ------------


@router.get("/settings/clinic", response_model=ClinicSettings)
async def get_clinic(db: DB, _: CurrentUser):
    s = await svc.clinic_settings(db)
    return {**s}


@router.put("/settings/clinic", response_model=ClinicSettings, dependencies=[Admin])
async def save_clinic(body: ClinicSettings, db: DB):
    await db.settings.update_one({"_id": "clinic"}, {"$set": body.model_dump()}, upsert=True)
    return body


def _admin_or_self(user: dict, doctor_id: str) -> None:
    if user["role"] != Role.ADMIN.value and str(user["_id"]) != doctor_id:
        raise Forbidden("Only an admin or the doctor can change this")


@router.put("/doctors/{doctor_id}/credentials", dependencies=[Clinical])
async def save_credentials(doctor_id: str, body: DoctorCredentials, db: DB, user: CurrentUser):
    """Registration number, council and qualifications printed on prescriptions."""
    _admin_or_self(user, doctor_id)
    doctor = await scheduling_service.get_doctor(db, doctor_id)
    await db.doctor_profiles.update_one({"_id": doctor["_id"]}, {"$set": body.model_dump()}, upsert=True)
    return body


@router.post("/doctors/{doctor_id}/signature", status_code=204, dependencies=[Clinical])
async def upload_signature(doctor_id: str, db: DB, user: CurrentUser, file: UploadFile = File(...)):
    """Signature image (PNG/JPG, max 1 MB) placed above the doctor's name on prescriptions."""
    _admin_or_self(user, doctor_id)
    doctor = await scheduling_service.get_doctor(db, doctor_id)
    data = await file.read()
    if len(data) > 1024 * 1024 or not (data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8")):
        raise Invalid("Upload a PNG or JPG image under 1 MB")
    file_id = await AsyncGridFSBucket(db, bucket_name="signatures").upload_from_stream(f"{doctor_id}-signature", data)
    await db.doctor_profiles.update_one({"_id": doctor["_id"]}, {"$set": {"signature_file_id": file_id}}, upsert=True)


@router.get("/doctors/{doctor_id}/signature", dependencies=[Clinical])
async def get_signature(doctor_id: str, db: DB):
    doctor = await scheduling_service.get_doctor(db, doctor_id)
    profile = await db.doctor_profiles.find_one({"_id": doctor["_id"]}) or {}
    if not profile.get("signature_file_id"):
        raise NotFound("No signature uploaded")
    stream = await AsyncGridFSBucket(db, bucket_name="signatures").open_download_stream(profile["signature_file_id"])
    data = await stream.read()
    return Response(data, media_type="image/png" if data.startswith(b"\x89PNG") else "image/jpeg")
