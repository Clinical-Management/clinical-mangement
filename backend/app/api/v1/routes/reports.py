from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from app.core.deps import DB, CurrentUser, require_roles
from app.schemas.report import ExportIn, FileCheckOut, ReportOut, ReportType, ReportUpdate
from app.schemas.user import Role
from app.services import report_service as svc

router = APIRouter(tags=["reports"])

Uploaders = Depends(require_roles(Role.ADMIN, Role.DOCTOR, Role.RECEPTIONIST, Role.PATIENT))


def _pdf(data: bytes, filename: str) -> Response:
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/patients/{patient_id}/reports/check", response_model=FileCheckOut, dependencies=[Uploaders])
async def check_upload(patient_id: str, db: DB, user: CurrentUser, file: UploadFile = File(...)):
    """Validate a file before uploading: type, size, readability, and image quality warnings."""
    patient = await svc.patient_for(db, patient_id, user)
    result, duplicate = await svc.check(db, patient["patient_id"], await file.read(), file.filename or "file")
    return {**result.__dict__, "ok": result.ok, "duplicate_of": duplicate}


@router.post("/patients/{patient_id}/reports", response_model=ReportOut, status_code=201, dependencies=[Uploaders])
async def upload_report(
    patient_id: str,
    db: DB,
    user: CurrentUser,
    file: UploadFile = File(..., description="The original file, stored unchanged"),
    processed: UploadFile | None = File(None, description="Enhanced copy of a camera capture (JPG/PNG)"),
    report_type: ReportType = Form(...),
    report_date: date = Form(...),
    ordering_doctor: str = Form(..., min_length=1, max_length=120),
    appointment_id: str | None = Form(None),
    title: str | None = Form(None, max_length=120),
    notes: str | None = Form(None, max_length=1000),
    source: Literal["upload", "camera"] = Form("upload"),
):
    return await svc.create_report(
        db,
        patient_id=patient_id,
        data=await file.read(),
        filename=file.filename or "report",
        processed=await processed.read() if processed else None,
        source=source,
        report_type=report_type,
        report_date=report_date,
        ordering_doctor=ordering_doctor,
        appointment_id=appointment_id or None,
        title=title,
        notes=notes,
        user=user,
    )


@router.get("/patients/{patient_id}/reports", response_model=list[ReportOut], dependencies=[Uploaders])
async def report_library(
    patient_id: str,
    db: DB,
    user: CurrentUser,
    report_type: ReportType | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    appointment_id: str | None = None,
):
    """A patient's reports, newest report date first, filterable by type, date range and visit."""
    patient = await svc.patient_for(db, patient_id, user)
    return await svc.list_reports(
        db, patient["patient_id"], report_type=report_type, date_from=date_from, date_to=date_to, appointment_id=appointment_id
    )


@router.post("/patients/{patient_id}/reports/export", dependencies=[Uploaders])
async def export_reports(patient_id: str, body: ExportIn, db: DB, user: CurrentUser):
    """Several reports in one PDF (cover page per report), e.g. to share with another doctor."""
    svc.ensure_can_view_files(user)
    patient = await svc.patient_for(db, patient_id, user)
    reports = await svc.reports_by_ids(db, patient["patient_id"], body.report_ids)
    return _pdf(await svc.export_pdf(db, reports), f"{patient['patient_id']}-reports.pdf")


@router.get("/reports/{report_id}", response_model=ReportOut, dependencies=[Uploaders])
async def get_report(report_id: str, db: DB, user: CurrentUser):
    return await svc.get_report(db, report_id, user)


@router.patch("/reports/{report_id}", response_model=ReportOut, dependencies=[Uploaders])
async def update_report(report_id: str, body: ReportUpdate, db: DB, user: CurrentUser):
    """Fix the tags (type, date, ordering doctor, visit). The file itself never changes."""
    return await svc.update_report(db, await svc.get_report(db, report_id, user), body, user)


@router.post("/reports/{report_id}/versions", response_model=ReportOut, dependencies=[Uploaders])
async def replace_file(
    report_id: str,
    db: DB,
    user: CurrentUser,
    file: UploadFile = File(...),
    processed: UploadFile | None = File(None),
    reason: str = Form(..., min_length=1, max_length=300),
    source: Literal["upload", "camera"] = Form("upload"),
):
    """Upload a replacement file. Earlier versions are kept."""
    report = await svc.get_report(db, report_id, user)
    return await svc.add_version(
        db, report, data=await file.read(), filename=file.filename or "report",
        processed=await processed.read() if processed else None, source=source, reason=reason, user=user,
    )


@router.get("/reports/{report_id}/file", dependencies=[Uploaders])
async def download_file(
    report_id: str,
    db: DB,
    user: CurrentUser,
    version: Annotated[int | None, Query(ge=1)] = None,
    rendition: Literal["original", "processed"] = "original",
    download: bool = False,
):
    svc.ensure_can_view_files(user)
    report = await svc.get_report(db, report_id, user)
    data, v, content_type = await svc.read_file(db, report, version, rendition)
    disposition = "attachment" if download else "inline"
    return Response(data, media_type=content_type, headers={"Content-Disposition": f'{disposition}; filename="{v["filename"]}"'})


@router.get("/reports/{report_id}/export", dependencies=[Uploaders])
async def export_report(report_id: str, db: DB, user: CurrentUser):
    svc.ensure_can_view_files(user)
    report = await svc.get_report(db, report_id, user)
    return _pdf(await svc.export_pdf(db, [report]), f"{report['patient_id']}-{report['report_type']}-{report['report_date']}.pdf")
