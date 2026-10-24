from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.core.deps import DB, CurrentUser, require_roles
from app.core.security import hash_password
from app.schemas.common import parse_object_id
from app.schemas.user import PasswordReset, Role, SecuritySettings, UserCreate, UserOut, UserUpdate
from app.services import audit_service, mfa_service
from app.services.user_service import EmailAlreadyRegistered, create_user

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles(Role.ADMIN))])


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_any_user(body: UserCreate, db: DB, admin: CurrentUser):
    """Create doctors (or other admins/patients) on their behalf."""
    try:
        user = await create_user(db, email=body.email, full_name=body.full_name, password=body.password, role=body.role)
    except EmailAlreadyRegistered:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    await audit_service.record(db, actor=admin, action="create", resource="users", resource_id=str(user["_id"]), details={"role": body.role.value})
    return user


@router.get("/users", response_model=list[UserOut])
async def list_users(
    db: DB,
    role: Role | None = None,
    staff: bool = False,
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    query = {"role": role.value} if role else {"role": {"$ne": Role.PATIENT.value}} if staff else {}
    return await db.users.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list()


async def _user(db, user_id: str) -> dict:
    oid = parse_object_id(user_id)
    user = oid and await db.users.find_one({"_id": oid})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: str, body: UserUpdate, db: DB, admin: CurrentUser):
    """Rename, change role, or deactivate (deactivated users can't sign in; their records stay)."""
    user = await _user(db, user_id)
    changes = body.model_dump(exclude_none=True)
    if "role" in changes:
        changes["role"] = changes["role"].value
    losing_admin = user["role"] == Role.ADMIN.value and (changes.get("role", "admin") != "admin" or changes.get("is_active") is False)
    if losing_admin and await db.users.count_documents({"role": "admin", "is_active": True}) <= 1:
        raise HTTPException(status_code=409, detail="Keep at least one active admin")
    if changes:
        await db.users.update_one({"_id": user["_id"]}, {"$set": changes})
        await audit_service.record(db, actor=admin, action="update", resource="users", resource_id=user_id,
                                   details={k: v for k, v in changes.items()})
    return await _user(db, user_id)


@router.post("/users/{user_id}/reset-mfa", status_code=204)
async def reset_mfa(user_id: str, db: DB, admin: CurrentUser):
    """For a lost phone: the user sets up two-step sign-in again at their next sign-in."""
    user = await _user(db, user_id)
    await mfa_service.disable(db, user["_id"])
    await audit_service.record(db, actor=admin, action="mfa_reset", resource="users", resource_id=user_id)


@router.post("/users/{user_id}/password", status_code=204)
async def reset_password(user_id: str, body: PasswordReset, db: DB, admin: CurrentUser):
    user = await _user(db, user_id)
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": hash_password(body.password)}, "$unset": {"locked_until": "", "failed_logins": ""}})
    await audit_service.record(db, actor=admin, action="password_reset", resource="users", resource_id=user_id)


@router.get("/security", response_model=SecuritySettings)
async def get_security(db: DB):
    return {"staff_mfa_required": await mfa_service.required(db)}


@router.put("/security", response_model=SecuritySettings)
async def save_security(body: SecuritySettings, db: DB, admin: CurrentUser):
    await db.settings.update_one({"_id": "security"}, {"$set": body.model_dump()}, upsert=True)
    await audit_service.record(db, actor=admin, action="update", resource="settings", resource_id="security", details=body.model_dump())
    return body


# --- audit log -------------------------------------------------------------------


def _filters(actor_id: str | None, patient_id: str | None, action: str | None, resource: str | None, date_from: date | None, date_to: date | None) -> dict:
    return {"actor_id": actor_id, "patient_id": patient_id, "action": action, "resource": resource, "date_from": date_from, "date_to": date_to}


def _view(e: dict) -> dict:
    return {**{k: v for k, v in e.items() if k != "_id"}, "id": str(e["_id"]), "actor_id": e["actor_id"] and str(e["actor_id"])}


@router.get("/audit")
async def audit_log(
    db: DB,
    actor_id: str | None = None,
    patient_id: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
):
    """Who viewed, created, edited or deleted what, newest first."""
    entries = await audit_service.list_entries(db, limit=limit, skip=skip, **_filters(actor_id, patient_id, action, resource, date_from, date_to))
    return [_view(e) for e in entries]


@router.get("/audit/verify")
async def verify_audit(db: DB):
    """Detects edited entries (bad signature) and deleted ones (missing sequence numbers)."""
    return await audit_service.verify(db)


@router.get("/audit/export")
async def export_audit(
    db: DB,
    actor_id: str | None = None,
    patient_id: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    data = await audit_service.export_csv(db, **_filters(actor_id, patient_id, action, resource, date_from, date_to))
    return Response(data, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'})


@router.get("/audit/activity")
async def staff_activity(db: DB, date_from: date | None = None, date_to: date | None = None):
    """Per staff member: actions by type and when they were last active."""
    return await audit_service.staff_activity(db, date_from=date_from, date_to=date_to)
