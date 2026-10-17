from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response

from app.core.deps import DB, CurrentUser, require_roles
from app.core.errors import Conflict, NotFound
from app.reports.summarizer import get_summary_engine
from app.schemas.summary import PatientSummaryOut, SummaryOut, TestAdd, TestEdit, TextEdit, TrendPoint
from app.schemas.user import Role
from app.services import report_service, summary_service as svc

router = APIRouter(tags=["report summaries"])

Clinical = Depends(require_roles(Role.ADMIN, Role.DOCTOR))
FileViewers = Depends(require_roles(Role.ADMIN, Role.DOCTOR, Role.PATIENT))

AI_LABEL = "AI-generated summary. Check against the original report before relying on it."
PATIENT_LABEL = "AI-generated summary, reviewed and approved by your doctor."


def get_summary_engine_factory():
    """Indirection so tests can swap the AI engine."""
    return get_summary_engine


EngineFactory = Annotated[object, Depends(get_summary_engine_factory)]


def summary_out(doc: dict) -> dict:
    label = svc.ASSISTIVE_LABEL if doc.get("document_kind") == "image_only" else AI_LABEL
    return {**doc, "label": label}


def patient_out(doc: dict) -> dict:
    return {**doc, "label": PATIENT_LABEL}


async def schedule(db, report: dict, background: BackgroundTasks, engine_factory) -> dict:
    """Create the summary record and read the report in the background (needs AI-processing consent)."""
    summary = await svc.start(db, report)
    if summary["status"] == "processing":
        background.add_task(svc.run, db, summary["_id"], engine_factory)
    return summary


@router.post("/reports/{report_id}/summary", response_model=SummaryOut, status_code=202, dependencies=[Clinical])
async def summarize(report_id: str, db: DB, user: CurrentUser, background: BackgroundTasks, engine: EngineFactory):
    """(Re-)run the AI summary for the report's current version. Clears any approval."""
    report = await report_service.get_report(db, report_id, user)
    return summary_out(await schedule(db, report, background, engine))


@router.get("/reports/{report_id}/summary", response_model=SummaryOut | PatientSummaryOut, dependencies=[FileViewers])
async def get_report_summary(report_id: str, db: DB, user: CurrentUser):
    """Doctors/admins get the full working summary; patients only an approved one."""
    report = await report_service.get_report(db, report_id, user)
    summary = await svc.latest_for_report(db, report)
    if user["role"] == Role.PATIENT.value:
        if not summary or summary["status"] != "approved":
            raise NotFound("No approved summary yet")
        return patient_out(summary)
    if not summary:
        raise NotFound("This report has not been summarised")
    return summary_out(summary)


@router.get("/reports/{report_id}/pages", dependencies=[FileViewers])
async def page_count(report_id: str, db: DB, user: CurrentUser, version: Annotated[int | None, Query(ge=1)] = None):
    report = await report_service.get_report(db, report_id, user)
    return {"count": len(await svc.report_pages(db, report, version))}


@router.get("/reports/{report_id}/pages/{page}", dependencies=[FileViewers])
async def page_image(report_id: str, page: int, db: DB, user: CurrentUser, version: Annotated[int | None, Query(ge=1)] = None):
    """Page image as read by the AI, for the side-by-side viewer (locations line up with it)."""
    report = await report_service.get_report(db, report_id, user)
    pages = await svc.report_pages(db, report, version)
    if not 1 <= page <= len(pages):
        raise NotFound("Page not found")
    return Response(pages[page - 1], media_type="image/png", headers={"Cache-Control": "private, max-age=600"})


@router.get("/patients/{patient_id}/report-summaries", response_model=list[PatientSummaryOut], dependencies=[FileViewers])
async def approved_for_patient(patient_id: str, db: DB, user: CurrentUser):
    """Approved summaries only: the feed for the patient view, case summary and prescriptions."""
    patient = await report_service.patient_for(db, patient_id, user)
    return [patient_out(s) for s in await svc.approved_summaries(db, patient["patient_id"])]


# --- doctor review -----------------------------------------------------------


async def summary_for(summary_id: str, db: DB, user: CurrentUser) -> dict:
    summary, _ = await svc.get_summary(db, summary_id, user)
    return summary


Summary = Annotated[dict, Depends(summary_for)]


@router.patch("/report-summaries/{summary_id}/tests/{test_id}", response_model=SummaryOut, dependencies=[Clinical])
async def edit_test(test_id: str, body: TestEdit, summary: Summary, db: DB, user: CurrentUser):
    """Correct an extracted value; flags are recomputed and the change is logged."""
    return summary_out(await svc.edit_test(db, summary, test_id, body.model_dump(exclude_unset=True), user))


@router.post("/report-summaries/{summary_id}/tests", response_model=SummaryOut, dependencies=[Clinical])
async def add_test(body: TestAdd, summary: Summary, db: DB, user: CurrentUser):
    return summary_out(await svc.add_test(db, summary, body.model_dump(), user))


@router.delete("/report-summaries/{summary_id}/tests/{test_id}", response_model=SummaryOut, dependencies=[Clinical])
async def remove_test(test_id: str, summary: Summary, db: DB, user: CurrentUser):
    return summary_out(await svc.remove_test(db, summary, test_id, user))


@router.patch("/report-summaries/{summary_id}/text", response_model=SummaryOut, dependencies=[Clinical])
async def edit_text(body: TextEdit, summary: Summary, db: DB, user: CurrentUser):
    return summary_out(await svc.edit_text(db, summary, body.model_dump(exclude_unset=True), user))


@router.post("/report-summaries/{summary_id}/approve", response_model=SummaryOut, dependencies=[Clinical])
async def approve(summary: Summary, db: DB, user: CurrentUser):
    """Only approved summaries reach the case summary, prescriptions and the patient."""
    if summary["status"] == "approved":
        raise Conflict("Already approved")
    return summary_out(await svc.approve(db, summary, user))


@router.get("/report-summaries/{summary_id}/trends", response_model=dict[str, list[TrendPoint]], dependencies=[Clinical])
async def trends(summary: Summary, db: DB):
    return await svc.trends(db, summary)
