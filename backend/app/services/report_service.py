import hashlib
from datetime import date, datetime, timezone

from gridfs import AsyncGridFSBucket
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.core import clock
from app.core.config import settings
from app.core.errors import Forbidden, Invalid, NotFound
from app.reports import export
from app.reports.files import KINDS, FileCheck, check_file, sniff
from app.schemas.common import parse_object_id
from app.schemas.report import REPORT_TYPE_LABELS, ReportType, ReportUpdate
from app.services import appointment_service, patient_service

UPLOADERS = {"admin", "doctor", "receptionist", "patient"}
CAN_VIEW_FILES = {"admin", "doctor", "patient"}  # receptionists upload but don't open clinical files


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bucket(db: AsyncDatabase) -> AsyncGridFSBucket:
    return AsyncGridFSBucket(db, bucket_name="report_files")


# --- access ------------------------------------------------------------------


async def patient_for(db: AsyncDatabase, patient_id: str, user: dict) -> dict:
    patient = await patient_service.get_patient(db, patient_id)
    if patient is None or (user["role"] == "patient" and patient.get("managed_by") != user["_id"]):
        raise NotFound("Patient not found")
    return patient


async def get_report(db: AsyncDatabase, report_id: str, user: dict) -> dict:
    oid = parse_object_id(report_id)
    report = oid and await db.reports.find_one({"_id": oid})
    if not report:
        raise NotFound("Report not found")
    await patient_for(db, report["patient_id"], user)
    return report


def ensure_can_view_files(user: dict) -> None:
    if user["role"] not in CAN_VIEW_FILES:
        raise Forbidden("Report files are available to clinical staff and the patient")


# --- checks ------------------------------------------------------------------


async def check(db: AsyncDatabase, patient_id: str, data: bytes, filename: str) -> tuple[FileCheck, str | None]:
    result = check_file(data, filename, settings.report_max_mb)
    duplicate = None
    if result.ok:
        existing = await db.reports.find_one(
            {"patient_id": patient_id, "versions.sha256": hashlib.sha256(data).hexdigest()}, {"_id": 1}
        )
        if existing:
            duplicate = str(existing["_id"])
            result.warnings.append("This exact file is already in the patient's reports.")
    return result, duplicate


def _check_processed(processed: bytes | None) -> None:
    if processed and sniff(processed) not in ("jpeg", "png"):
        raise Invalid("The enhanced copy must be a JPG or PNG image")


def _quality_from_processed(result: FileCheck, processed: bytes | None) -> None:
    """For camera captures, judge blur/skew/resolution on the cropped, enhanced copy that people
    will read (the raw photo is naturally skewed); the original is still validated and stored."""
    if not processed:
        return
    enhanced = check_file(processed, "enhanced", settings.report_max_mb)
    keep = [w for w in result.warnings if "already in the patient" in w]
    result.warnings = keep + enhanced.warnings
    result.info["enhanced"] = {k: enhanced.info.get(k) for k in ("width", "height", "sharpness", "skew_degrees")}


async def _visit(db: AsyncDatabase, appointment_id: str | None, patient_id: str, user: dict) -> dict | None:
    if not appointment_id:
        return None
    appt = await appointment_service.get_for_user(db, appointment_id, user)
    if appt["patient_id"] != patient_id:
        raise Invalid("That visit belongs to a different patient")
    return appt


def _validate_meta(report_date: date | None, ordering_doctor: str | None) -> None:
    if report_date and report_date > clock.clinic_today():
        raise Invalid("Report date cannot be in the future")
    if ordering_doctor is not None and not ordering_doctor.strip():
        raise Invalid("Ordering doctor is required")


# --- storage -----------------------------------------------------------------


async def _store_version(
    db: AsyncDatabase,
    *,
    patient_id: str,
    version: int,
    data: bytes,
    filename: str,
    processed: bytes | None,
    source: str,
    result: FileCheck,
    reason: str | None,
    user: dict,
) -> dict:
    bucket = _bucket(db)
    meta = {"patient_id": patient_id, "version": version}
    # The original bytes are stored exactly as received and never rewritten
    file_id = await bucket.upload_from_stream(filename, data, metadata={**meta, "rendition": "original"})
    processed_id = None
    if processed:
        processed_id = await bucket.upload_from_stream(
            f"enhanced-{filename}", processed, metadata={**meta, "rendition": "processed"}
        )
    return {
        "version": version,
        "file_id": file_id,
        "processed_file_id": processed_id,
        "has_processed": processed_id is not None,
        "filename": filename,
        "content_type": result.content_type,
        "kind": result.kind,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "source": source,
        "warnings": result.warnings,
        "info": result.info,
        "reason": reason,
        "uploaded_at": _now(),
        "uploaded_by": user["_id"],
        "uploaded_by_role": user["role"],
    }


async def create_report(
    db: AsyncDatabase,
    *,
    patient_id: str,
    data: bytes,
    filename: str,
    processed: bytes | None,
    source: str,
    report_type: ReportType,
    report_date: date,
    ordering_doctor: str,
    appointment_id: str | None,
    title: str | None,
    notes: str | None,
    user: dict,
) -> dict:
    patient = await patient_for(db, patient_id, user)
    _validate_meta(report_date, ordering_doctor)
    appt = await _visit(db, appointment_id, patient["patient_id"], user)
    _check_processed(processed)
    result, _ = await check(db, patient["patient_id"], data, filename)
    if not result.ok:
        raise Invalid(" ".join(result.errors))
    _quality_from_processed(result, processed)

    version = await _store_version(
        db, patient_id=patient["patient_id"], version=1, data=data, filename=filename,
        processed=processed, source=source, result=result, reason=None, user=user,
    )
    now = _now()
    doc = {
        "patient_id": patient["patient_id"],
        "patient_name": patient["full_name"],
        "appointment_id": appt["_id"] if appt else None,
        "visit_date": appt["date"] if appt else None,
        "report_type": report_type.value,
        "report_date": report_date.isoformat(),
        "ordering_doctor": ordering_doctor.strip(),
        "title": (title or "").strip() or None,
        "notes": (notes or "").strip() or None,
        "current_version": 1,
        "versions": [version],
        "created_at": now,
        "created_by": user["_id"],
        "updated_at": now,
    }
    await db.reports.insert_one(doc)
    return doc


async def add_version(
    db: AsyncDatabase, report: dict, *, data: bytes, filename: str, processed: bytes | None, source: str, reason: str, user: dict
) -> dict:
    """Replace the file: earlier versions are kept and stay downloadable."""
    if not reason.strip():
        raise Invalid("Please say why the file is being replaced")
    _check_processed(processed)
    result, _ = await check(db, report["patient_id"], data, filename)
    if not result.ok:
        raise Invalid(" ".join(result.errors))
    _quality_from_processed(result, processed)
    version = await _store_version(
        db, patient_id=report["patient_id"], version=report["current_version"] + 1, data=data, filename=filename,
        processed=processed, source=source, result=result, reason=reason.strip(), user=user,
    )
    return await db.reports.find_one_and_update(
        {"_id": report["_id"], "current_version": report["current_version"]},
        {"$set": {"current_version": version["version"], "updated_at": _now()}, "$push": {"versions": version}},
        return_document=ReturnDocument.AFTER,
    ) or await db.reports.find_one({"_id": report["_id"]})


async def update_report(db: AsyncDatabase, report: dict, data: ReportUpdate, user: dict) -> dict:
    sets = data.model_dump(exclude_unset=True, mode="json")
    _validate_meta(data.report_date, data.ordering_doctor)
    if "appointment_id" in sets:
        appt = await _visit(db, sets["appointment_id"], report["patient_id"], user)
        sets["appointment_id"] = appt["_id"] if appt else None
        sets["visit_date"] = appt["date"] if appt else None
    if "ordering_doctor" in sets:
        sets["ordering_doctor"] = sets["ordering_doctor"].strip()
    sets["updated_at"] = _now()
    return await db.reports.find_one_and_update({"_id": report["_id"]}, {"$set": sets}, return_document=ReturnDocument.AFTER)


async def list_reports(
    db: AsyncDatabase,
    patient_id: str,
    *,
    report_type: ReportType | None,
    date_from: date | None,
    date_to: date | None,
    appointment_id: str | None,
) -> list[dict]:
    query: dict = {"patient_id": patient_id}
    if report_type:
        query["report_type"] = report_type.value
    if date_from or date_to:
        query["report_date"] = {
            **({"$gte": date_from.isoformat()} if date_from else {}),
            **({"$lte": date_to.isoformat()} if date_to else {}),
        }
    if appointment_id:
        query["appointment_id"] = parse_object_id(appointment_id)
    return await db.reports.find(query).sort([("report_date", -1), ("created_at", -1)]).to_list(500)


def _version(report: dict, version: int | None) -> dict:
    wanted = version or report["current_version"]
    found = next((v for v in report["versions"] if v["version"] == wanted), None)
    if not found:
        raise NotFound("Version not found")
    return found


async def read_file(db: AsyncDatabase, report: dict, version: int | None, rendition: str) -> tuple[bytes, dict, str]:
    """rendition: "original" (exactly as uploaded) or "processed" (enhanced camera copy, if any)."""
    v = _version(report, version)
    use_processed = rendition == "processed" and v.get("processed_file_id") is not None
    stream = await _bucket(db).open_download_stream(v["processed_file_id"] if use_processed else v["file_id"])
    data = await stream.read()
    return data, v, KINDS[sniff(data)] if use_processed else v["content_type"]


async def export_pdf(db: AsyncDatabase, reports: list[dict]) -> bytes:
    parts = []
    for report in reports:
        v = _version(report, None)
        # Readable rendition for photos (enhanced copy when there is one); PDFs/DICOM as stored
        data, _, _ = await read_file(db, report, None, "processed" if v["kind"] in ("jpeg", "png") else "original")
        parts.append(
            {
                "title": f"{REPORT_TYPE_LABELS[report['report_type']]} report",
                "kind": v["kind"] if v["kind"] in ("pdf", "dicom") else "image",
                "data": data,
                "lines": [
                    ("Patient", f"{report['patient_name']} ({report['patient_id']})"),
                    ("Report date", report["report_date"]),
                    ("Ordering doctor", report["ordering_doctor"]),
                    ("Title", report.get("title") or ""),
                    ("Original file", f"{v['filename']} (version {v['version']})"),
                    ("Uploaded", f"{v['uploaded_at']:%d %b %Y} by {v['uploaded_by_role']}"),
                ],
            }
        )
    return export.build_pdf(parts)


async def reports_by_ids(db: AsyncDatabase, patient_id: str, ids: list[str]) -> list[dict]:
    oids = [oid for i in ids if (oid := parse_object_id(i))]
    found = await db.reports.find({"_id": {"$in": oids}, "patient_id": patient_id}).to_list(len(oids))
    if len(found) != len(set(ids)):
        raise NotFound("Some reports were not found for this patient")
    order = {oid: n for n, oid in enumerate(oids)}
    return sorted(found, key=lambda r: order[r["_id"]])

