from pymongo.asynchronous.database import AsyncDatabase

from app.schemas.common import parse_object_id


async def past_visits(db: AsyncDatabase, patient_id: str, *, exclude_appointment: str | None) -> list[dict]:
    """Earlier completed visits (any doctor, so care is continuous) with what was found and prescribed."""
    query: dict = {"patient_id": patient_id, "status": "completed"}
    if exclude_appointment and (oid := parse_object_id(exclude_appointment)):
        query["_id"] = {"$ne": oid}
    appts = await db.appointments.find(query).sort([("date", -1), ("start_time", -1)]).to_list(100)
    ids = [a["_id"] for a in appts]

    notes = {n["appointment_id"]: n for n in await db.clinical_notes.find({"appointment_id": {"$in": ids}}).to_list(None)}
    rx = {p["appointment_id"]: p for p in await db.prescriptions.find({"appointment_id": {"$in": ids}}).to_list(None)}
    histories = {
        h["appointment_id"]: h
        for h in await db.history_sessions.find({"appointment_id": {"$in": ids}, "status": "submitted"}).to_list(None)
    }

    visits = []
    for a in appts:
        n, p, h = notes.get(a["_id"], {}), rx.get(a["_id"]), histories.get(a["_id"])
        visits.append(
            {
                "appointment_id": str(a["_id"]),
                "date": a["date"],
                "doctor_name": a["doctor_name"],
                "visit_type": a["visit_type"],
                "chief_complaint": ((h or {}).get("fields", {}).get("chief_complaint") or {}).get("value") or None,
                "history_summary": (h or {}).get("summary"),
                "examination": n.get("examination") or None,
                "diagnoses": [
                    {"code": d["code"], "title": d["title"], "status": d["status"]} for d in n.get("diagnoses", [])
                ],
                "outcome": n.get("outcome"),
                "medicines": (p or {}).get("medicines", []),
                "investigations": (p or {}).get("investigations", []),
                "advice": (p or {}).get("advice") or None,
                "follow_up": (p or {}).get("follow_up"),
                "vitals_flag": a.get("vitals_flag"),
                "payment_status": a["payment_status"],
            }
        )
    return visits
