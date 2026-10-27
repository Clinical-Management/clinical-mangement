import re
from datetime import date, datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.schemas.patient import Communication, ConsentIn, MedicalInfo, PatientCreate, PatientDemographics


class DuplicatePatient(Exception):
    def __init__(self, matches: list[dict]):
        self.matches = matches


# --- normalisation -----------------------------------------------------------


def phone_key(phone: str) -> str:
    """Digits only, last 10 kept so "+91 98765 43210" and "9876543210" match."""
    digits = re.sub(r"\D", "", phone)
    return digits[-10:]


def name_key(name: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", name.lower()).split())


def _years_between(start: date, end: date) -> int:
    return end.year - start.year - ((end.month, end.day) < (start.month, start.day))


def current_age(doc: dict, today: date | None = None) -> int | None:
    today = today or date.today()
    if doc.get("date_of_birth"):
        return _years_between(date.fromisoformat(doc["date_of_birth"]), today)
    if doc.get("stated_age") is not None:
        # Age was given instead of DOB: advance it by the time since it was recorded
        return doc["stated_age"] + _years_between(doc["stated_age_at"].date(), today)
    return None


def has_voicebot_consent(doc: dict) -> bool:
    """Gate for the voicebot: it may only be used with all three consents."""
    c = doc["consent"]
    return c["data_storage"] and c["voice_recording"] and c["ai_processing"]


def to_public(doc: dict) -> dict:
    return {**doc, "age": current_age(doc), "voicebot_allowed": has_voicebot_consent(doc)}


# --- persistence -------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _next_patient_id(db: AsyncDatabase) -> str:
    counter = await db.counters.find_one_and_update(
        {"_id": "patient"}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return f"CMP-{counter['seq']:06d}"


def _demographic_fields(data: PatientDemographics, now: datetime) -> dict:
    fields = data.model_dump(mode="json", include=set(PatientDemographics.model_fields) - {"age"})
    fields["phone_key"] = phone_key(data.phone)
    fields["name_key"] = name_key(data.full_name)
    # DOB wins over age; when only age is known, remember when it was stated
    fields["stated_age"] = None if data.date_of_birth else data.age
    fields["stated_age_at"] = None if data.date_of_birth else now
    if fields.get("communication") is None:
        fields.pop("communication", None)
    return fields


def _consent_record(consent: ConsentIn, actor: dict, now: datetime) -> dict:
    return {**consent.model_dump(), "updated_at": now, "updated_by": actor["_id"], "updated_by_role": actor["role"]}


async def find_duplicates(db: AsyncDatabase, data: PatientDemographics) -> list[dict]:
    """Same phone AND (same name OR same date of birth)."""
    key_name = name_key(data.full_name)
    dob = data.date_of_birth.isoformat() if data.date_of_birth else None
    either = [{"name_key": key_name}] + ([{"date_of_birth": dob}] if dob else [])
    docs = await db.patients.find({"phone_key": phone_key(data.phone), "$or": either}).to_list(20)
    return [
        {
            **to_public(d),
            "matched_on": ["phone"]
            + (["name"] if d["name_key"] == key_name else [])
            + (["date_of_birth"] if dob and d.get("date_of_birth") == dob else []),
        }
        for d in docs
    ]


async def create_patient(db: AsyncDatabase, data: PatientCreate, *, actor: dict, managed_by: ObjectId | None) -> dict:
    matches = await find_duplicates(db, data)
    if matches and not data.allow_duplicate:
        raise DuplicatePatient(matches)

    now = _now()
    consent = _consent_record(data.consent, actor, now)
    doc = {
        "patient_id": await _next_patient_id(db),
        **_demographic_fields(data, now),
        "managed_by": managed_by,
        "consent": consent,
        "consent_history": [consent],
        "medical": MedicalInfo().model_dump(),
        "communication": (data.communication or Communication()).model_dump(),
        # Kept so admins can review records registered despite a duplicate warning
        "possible_duplicates": [m["patient_id"] for m in matches],
        "created_at": now,
        "created_by": actor["_id"],
        "updated_at": now,
    }
    await db.patients.insert_one(doc)
    return doc


async def get_patient(db: AsyncDatabase, patient_id: str) -> dict | None:
    return await db.patients.find_one({"patient_id": patient_id.upper()})


async def update_demographics(db: AsyncDatabase, patient_id: str, data: PatientDemographics) -> dict:
    now = _now()
    return await db.patients.find_one_and_update(
        {"patient_id": patient_id},
        {"$set": {**_demographic_fields(data, now), "updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )


async def update_medical(db: AsyncDatabase, patient_id: str, medical: MedicalInfo, *, actor: dict) -> dict:
    now = _now()
    return await db.patients.find_one_and_update(
        {"patient_id": patient_id},
        {
            "$set": {
                "medical": medical.model_dump(mode="json"),
                "medical_updated_at": now,
                "medical_updated_by": actor["_id"],
                "medical_updated_by_role": actor["role"],
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )


async def update_consent(db: AsyncDatabase, patient_id: str, consent: ConsentIn, *, actor: dict) -> dict:
    now = _now()
    record = _consent_record(consent, actor, now)
    return await db.patients.find_one_and_update(
        {"patient_id": patient_id},
        {"$set": {"consent": record, "updated_at": now}, "$push": {"consent_history": record}},
        return_document=ReturnDocument.AFTER,
    )


async def search_patients(
    db: AsyncDatabase, *, q: str | None, flagged: bool, limit: int, skip: int
) -> list[dict]:
    query: dict = {}
    if q and q.strip():
        q = q.strip()
        ors: list[dict] = [
            {"patient_id": q.upper()},
            {"name_key": {"$regex": re.escape(name_key(q))}},
        ]
        if len(digits := re.sub(r"\D", "", q)) >= 4:
            ors.append({"phone_key": {"$regex": re.escape(digits[-10:])}})
        query["$or"] = ors
    if flagged:
        query["possible_duplicates.0"] = {"$exists": True}
    return await db.patients.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list()


async def list_managed(db: AsyncDatabase, user_id: ObjectId) -> list[dict]:
    return await db.patients.find({"managed_by": user_id}).sort("created_at", 1).to_list(50)


async def family_of(db: AsyncDatabase, doc: dict, *, owner_view: bool) -> list[dict]:
    """Owners see the profiles they manage; staff also see everyone sharing the phone number."""
    ors: list[dict] = []
    if doc.get("managed_by"):
        ors.append({"managed_by": doc["managed_by"]})
    if not owner_view:
        ors.append({"phone_key": doc["phone_key"]})
    if not ors:
        return []
    return await db.patients.find({"$or": ors, "_id": {"$ne": doc["_id"]}}).sort("created_at", 1).to_list(50)
