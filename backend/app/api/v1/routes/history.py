from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.security import HTTPAuthorizationCredentials

from app.core.deps import DB, CurrentUser, bearer_scheme, get_current_user, require_roles
from app.core.errors import Conflict
from app.history import service as svc
from app.history.engine import get_engine
from app.history.fields import FIELDS_BY_KEY
from app.schemas.history import (
    AlertOut,
    FieldReviewIn,
    LanguageIn,
    ManualFieldsIn,
    PatientMessageIn,
    PatientSessionView,
    SessionCreate,
    SessionOut,
    SessionStarted,
    SummaryIn,
)
from app.schemas.user import Role

router = APIRouter(tags=["history"])

Clinical = Depends(require_roles(Role.ADMIN, Role.DOCTOR))
Staff = Depends(require_roles(Role.ADMIN, Role.RECEPTIONIST, Role.DOCTOR))


def get_engine_factory():
    """Indirection so tests can swap the AI engine; the engine is only built when needed."""
    return get_engine


EngineFactory = Annotated[object, Depends(get_engine_factory)]


def patient_view(doc: dict) -> dict:
    return {**doc, "patient_first_name": doc["patient_context"]["first_name"]}


def clinical_view(doc: dict) -> dict:
    fields = [
        {
            "key": key,
            "label": FIELDS_BY_KEY[key].label,
            "section": FIELDS_BY_KEY[key].section,
            "value": doc["fields"][key]["value"],
            "origin": doc["fields"][key]["origin"],
            "review_status": doc["review"].get(key),
        }
        for key in doc["applicable_fields"]
    ]
    return {**doc, "fields": fields}


def _started(doc: dict, token: str | None) -> dict:
    link = token and {"token": token, "path": f"/voice/{doc['_id']}?token={token}", "expires_at": doc["link_expires_at"]}
    return {"session": patient_view(doc), "link": link}


async def patient_side_session(
    session_id: str,
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    x_history_token: Annotated[str | None, Header()] = None,
) -> dict:
    """Patient-facing endpoints accept either a kiosk/phone link token or a login."""
    doc = await svc.get_session(db, session_id)
    if x_history_token:
        svc.check_link(doc, x_history_token)
    else:
        user = await get_current_user(db, credentials)
        await svc.check_user_access(db, doc, user)
    return doc


PatientSide = Annotated[dict, Depends(patient_side_session)]


async def clinical_session(session_id: str, db: DB, user: CurrentUser) -> dict:
    doc = await svc.get_session(db, session_id)
    await svc.check_user_access(db, doc, user, clinical=True)
    return doc


ClinicalSession = Annotated[dict, Depends(clinical_session)]


# --- starting ----------------------------------------------------------------


@router.post(
    "/history/sessions",
    response_model=SessionStarted,
    status_code=201,
    dependencies=[Depends(require_roles(Role.ADMIN, Role.RECEPTIONIST, Role.DOCTOR, Role.PATIENT))],
)
async def start_session(body: SessionCreate, db: DB, user: CurrentUser):
    """Start (or resume) pre-visit history for an appointment. Kiosk/phone channels get a link."""
    doc, token = await svc.start_session(
        db, appointment_id=body.appointment_id, mode=body.mode, channel=body.channel, language=body.language, actor=user
    )
    return _started(doc, token)


@router.post("/history/sessions/{session_id}/link", response_model=SessionStarted, dependencies=[Staff])
async def new_link(session_id: str, db: DB, user: CurrentUser):
    doc = await svc.get_session(db, session_id)
    if user["role"] == Role.DOCTOR.value:
        await svc.check_user_access(db, doc, user, clinical=True)
    doc, token = await svc.reissue_link(db, doc)
    return _started(doc, token)


# --- patient side ------------------------------------------------------------


@router.get("/history/sessions/{session_id}/patient-view", response_model=PatientSessionView)
async def get_patient_view(doc: PatientSide):
    return patient_view(doc)


@router.post("/history/sessions/{session_id}/messages", response_model=PatientSessionView)
async def send_message(body: PatientMessageIn, doc: PatientSide, db: DB, engine: EngineFactory):
    return patient_view(await svc.patient_message(db, doc, body.text, body.input, engine))


@router.put("/history/sessions/{session_id}/language", response_model=PatientSessionView)
async def change_language(body: LanguageIn, doc: PatientSide, db: DB):
    return patient_view(await svc.set_language(db, doc, body.language))


@router.post("/history/sessions/{session_id}/finish", response_model=PatientSessionView)
async def finish(doc: PatientSide, db: DB, engine: EngineFactory):
    """Patient wants to stop: show the read-back summary."""
    return patient_view(await svc.finish(db, doc, engine))


@router.post("/history/sessions/{session_id}/correct", response_model=PatientSessionView)
async def correct(body: PatientMessageIn, doc: PatientSide, db: DB, engine: EngineFactory):
    return patient_view(await svc.correct(db, doc, body.text, body.input, engine))


@router.post("/history/sessions/{session_id}/submit", response_model=PatientSessionView)
async def submit_from_patient(doc: PatientSide, db: DB, engine: EngineFactory):
    if doc["mode"] == "manual":
        raise Conflict("This history is being entered by staff")
    return patient_view(await svc.submit(db, doc, engine))


# --- clinical side -----------------------------------------------------------


@router.get("/history/sessions", response_model=list[SessionOut], dependencies=[Clinical])
async def list_sessions(db: DB, user: CurrentUser, appointment_id: str | None = None, patient_id: str | None = None):
    return [clinical_view(d) for d in await svc.list_sessions(db, user, appointment_id=appointment_id, patient_id=patient_id)]


@router.get("/history/sessions/{session_id}", response_model=SessionOut)
async def get_session(doc: ClinicalSession):
    return clinical_view(doc)


@router.put("/history/sessions/{session_id}/manual", response_model=SessionOut)
async def save_manual(body: ManualFieldsIn, doc: ClinicalSession, db: DB, user: CurrentUser):
    """Staff entry when voice/AI is not used. Call /manual/submit when done."""
    return clinical_view(await svc.save_manual(db, doc, body.fields, user))


@router.post("/history/sessions/{session_id}/manual/submit", response_model=SessionOut)
async def submit_manual(doc: ClinicalSession, db: DB, engine: EngineFactory):
    return clinical_view(await svc.submit(db, doc, engine))


@router.put("/history/sessions/{session_id}/fields/{key}", response_model=SessionOut)
async def review_field(key: str, body: FieldReviewIn, doc: ClinicalSession, db: DB, user: CurrentUser):
    """Doctor accepts, rejects or edits an extracted field (logged)."""
    return clinical_view(await svc.review_field(db, doc, key, body.action, body.value, user))


@router.put("/history/sessions/{session_id}/summary", response_model=SessionOut)
async def edit_summary(body: SummaryIn, doc: ClinicalSession, db: DB, user: CurrentUser):
    return clinical_view(await svc.edit_summary(db, doc, body.summary, user))


# --- alerts ------------------------------------------------------------------


@router.get("/alerts", response_model=list[AlertOut], dependencies=[Staff])
async def list_alerts(db: DB, user: CurrentUser, open_only: bool = Query(True)):
    """Red-flag alerts from the last 24 hours. Doctors see their own patients'."""
    return await svc.list_alerts(db, user, open_only=open_only)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut, dependencies=[Staff])
async def acknowledge(alert_id: str, db: DB, user: CurrentUser):
    return await svc.acknowledge_alert(db, alert_id, user)
