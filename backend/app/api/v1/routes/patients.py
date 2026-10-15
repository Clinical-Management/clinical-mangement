from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import DB, CurrentUser, require_roles
from app.schemas.patient import (
    ConsentIn,
    DuplicateMatch,
    MedicalInfo,
    PatientCreate,
    PatientDemographics,
    PatientOut,
    Relationship,
)
from app.schemas.user import Role
from app.services import patient_service as svc

router = APIRouter(prefix="/patients", tags=["patients"])

# Front-desk staff handle registration but don't need clinical details
MEDICAL_HIDDEN_FROM = {Role.RECEPTIONIST.value}


def present(doc: dict, user: dict) -> dict:
    out = svc.to_public(doc)
    if user["role"] in MEDICAL_HIDDEN_FROM:
        out.update(medical=None, medical_updated_at=None, medical_updated_by_role=None)
    return out


async def load_patient(db, patient_id: str, user: dict) -> dict:
    """Staff can open any record; a patient account only the profiles it manages."""
    doc = await svc.get_patient(db, patient_id)
    if doc is None or (user["role"] == Role.PATIENT.value and doc.get("managed_by") != user["_id"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return doc


@router.post(
    "",
    response_model=PatientOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(Role.ADMIN, Role.RECEPTIONIST, Role.PATIENT))],
)
async def register_patient(body: PatientCreate, db: DB, user: CurrentUser):
    """Admins and receptionists register walk-ins; patient accounts register themselves and family members.

    Returns 409 with possible matches (same phone + same name or DOB) unless
    `allow_duplicate` is set.
    """
    is_owner = user["role"] == Role.PATIENT.value
    if is_owner:
        if body.relationship is None:
            raise HTTPException(status_code=422, detail="Relationship is required for family profiles")
        if body.relationship == Relationship.SELF and await db.patients.find_one(
            {"managed_by": user["_id"], "relationship": Relationship.SELF.value}
        ):
            raise HTTPException(status_code=409, detail="You already have your own profile")

    try:
        doc = await svc.create_patient(db, body, actor=user, managed_by=user["_id"] if is_owner else None)
    except svc.DuplicatePatient as dup:
        # Patient accounts only get details of matches they manage themselves
        visible = [m for m in dup.matches if not is_owner or m.get("managed_by") == user["_id"]]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "possible_duplicate",
                "message": "A patient with this phone number and the same name or date of birth already exists.",
                "matches": [DuplicateMatch.model_validate(m).model_dump(mode="json") for m in visible],
            },
        )
    return present(doc, user)


@router.get("", response_model=list[PatientOut])
async def list_patients(
    db: DB,
    user: CurrentUser,
    q: str | None = Query(None, max_length=100, description="Patient ID, name or phone"),
    flagged: bool = Query(False, description="Only records registered despite a duplicate warning"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    if user["role"] == Role.PATIENT.value:
        docs = await svc.list_managed(db, user["_id"])
    else:
        docs = await svc.search_patients(db, q=q, flagged=flagged, limit=limit, skip=skip)
    return [present(d, user) for d in docs]


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(patient_id: str, db: DB, user: CurrentUser):
    return present(await load_patient(db, patient_id, user), user)


@router.put("/{patient_id}", response_model=PatientOut)
async def update_patient(patient_id: str, body: PatientDemographics, db: DB, user: CurrentUser):
    if user["role"] == Role.DOCTOR.value:
        raise HTTPException(status_code=403, detail="Doctors cannot edit registration details")
    doc = await load_patient(db, patient_id, user)
    if doc.get("relationship") == Relationship.SELF.value and body.relationship != Relationship.SELF:
        raise HTTPException(status_code=422, detail="The account holder's own profile must stay 'self'")
    return present(await svc.update_demographics(db, doc["patient_id"], body), user)


@router.put("/{patient_id}/medical", response_model=PatientOut)
async def update_medical(patient_id: str, body: MedicalInfo, db: DB, user: CurrentUser):
    """Allergies, chronic conditions and current medicines. Patients may self-report;
    the role of the last editor is shown on the profile."""
    if user["role"] in MEDICAL_HIDDEN_FROM:
        raise HTTPException(status_code=403, detail="Receptionists cannot edit medical information")
    doc = await load_patient(db, patient_id, user)
    return present(await svc.update_medical(db, doc["patient_id"], body, actor=user), user)


@router.put("/{patient_id}/consent", response_model=PatientOut)
async def update_consent(patient_id: str, body: ConsentIn, db: DB, user: CurrentUser):
    """Every change is appended to the record's consent history."""
    doc = await load_patient(db, patient_id, user)
    return present(await svc.update_consent(db, doc["patient_id"], body, actor=user), user)


@router.get("/{patient_id}/family", response_model=list[PatientOut])
async def get_family(patient_id: str, db: DB, user: CurrentUser):
    doc = await load_patient(db, patient_id, user)
    docs = await svc.family_of(db, doc, owner_view=user["role"] == Role.PATIENT.value)
    return [present(d, user) for d in docs]
