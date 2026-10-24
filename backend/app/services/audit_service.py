"""Tamper-evident audit log of who viewed, created, edited or deleted records.

Entries are insert-only. Each gets the next number in an unbroken sequence and an HMAC signature over its
contents, so `verify` detects an edited entry (bad signature) and a deleted one (gap in the sequence)."""

import csv
import hashlib
import hmac
import io
import json
import re
from datetime import date, datetime, time, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings
from app.schemas.common import parse_object_id

SIGNED_FIELDS = ("seq", "at", "actor_id", "actor_role", "action", "resource", "resource_id", "patient_id", "method", "path", "status", "ip", "details")


def _key() -> bytes:
    return (settings.audit_signing_key or "audit:" + settings.jwt_secret).encode()


def _canonical(entry: dict) -> bytes:
    data = {k: entry.get(k) for k in SIGNED_FIELDS}
    data["at"] = entry["at"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    data["actor_id"] = str(data["actor_id"]) if data["actor_id"] else None
    return json.dumps(data, sort_keys=True, default=str, separators=(",", ":")).encode()


def _sign(entry: dict) -> str:
    return hmac.new(_key(), _canonical(entry), hashlib.sha256).hexdigest()


async def record(
    db: AsyncDatabase,
    *,
    actor: dict | None,
    action: str,
    resource: str,
    resource_id: str | None = None,
    patient_id: str | None = None,
    details: dict | None = None,
    method: str | None = None,
    path: str | None = None,
    status: int | None = None,
    ip: str | None = None,
    actor_id: ObjectId | None = None,
    actor_role: str | None = None,
) -> None:
    counter = await db.counters.find_one_and_update(
        {"_id": "audit"}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    now = datetime.now(timezone.utc)
    entry = {
        "seq": counter["seq"],
        "at": now.replace(microsecond=now.microsecond // 1000 * 1000),  # Mongo keeps milliseconds
        "actor_id": actor["_id"] if actor else actor_id,
        "actor_role": actor["role"] if actor else actor_role,
        "action": action,
        "resource": resource,
        "resource_id": resource_id,
        "patient_id": patient_id,
        "method": method,
        "path": path,
        "status": status,
        "ip": ip,
        "details": details or {},
    }
    entry["sig"] = _sign(entry)
    await db.audit_log.insert_one(entry)


# --- request logging -----------------------------------------------------------

# Patient-scoped resources: views of these are logged; list and polling endpoints are not
_SCOPED = re.compile(r"^/(patients|appointments|reports|report-summaries|history|prescription-versions|bills|receipts)/([^/]+)(/.*)?$")
_SKIP = re.compile(r"^/(auth/|alerts|health|public/|ml/)")
_ACTIONS = {"GET": "view", "POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}


async def _patient_for(db: AsyncDatabase, resource: str, resource_id: str) -> str | None:
    if resource == "patients":
        return resource_id
    oid = parse_object_id(resource_id)
    if not oid:
        return None
    collection = {"appointments": "appointments", "reports": "reports", "history": "history_sessions", "bills": "bills", "receipts": "receipts"}.get(resource)
    if collection:
        doc = await db[collection].find_one({"_id": oid}, {"patient_id": 1})
        return doc and doc.get("patient_id")
    return None


async def log_request(db: AsyncDatabase, *, path: str, method: str, status: int, claims: dict, ip: str | None) -> None:
    """Called by the HTTP middleware after an authenticated API request."""
    if method not in _ACTIONS or _SKIP.match(path):
        return
    scoped = _SCOPED.match(path)
    if method == "GET" and not scoped:
        return
    resource = scoped.group(1) if scoped else path.strip("/").split("/")[0]
    resource_id = scoped.group(2) if scoped else None
    action = "denied" if status == 403 else _ACTIONS[method]
    await record(
        db,
        actor=None,
        actor_id=parse_object_id(claims.get("sub", "")),
        actor_role=claims.get("role"),
        action=action,
        resource=resource,
        resource_id=resource_id,
        patient_id=scoped and await _patient_for(db, resource, resource_id),
        method=method,
        path=path,
        status=status,
        ip=ip,
    )


# --- reading -------------------------------------------------------------------


def _query(*, actor_id=None, patient_id=None, action=None, resource=None, date_from: date | None = None, date_to: date | None = None) -> dict:
    q: dict = {}
    if actor_id and (oid := parse_object_id(actor_id)):
        q["actor_id"] = oid
    if patient_id:
        q["patient_id"] = patient_id.upper()
    if action:
        q["action"] = action
    if resource:
        q["resource"] = resource
    if date_from or date_to:
        q["at"] = {}
        if date_from:
            q["at"]["$gte"] = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        if date_to:
            q["at"]["$lte"] = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
    return q


async def _with_names(db: AsyncDatabase, entries: list[dict]) -> list[dict]:
    ids = {e["actor_id"] for e in entries if e.get("actor_id")}
    users = {u["_id"]: u for u in await db.users.find({"_id": {"$in": list(ids)}}, {"full_name": 1, "email": 1}).to_list(None)}
    for e in entries:
        u = users.get(e.get("actor_id"))
        e["actor_name"] = u["full_name"] if u else None
        e["actor_email"] = u["email"] if u else None
    return entries


async def list_entries(db: AsyncDatabase, *, limit: int = 100, skip: int = 0, **filters) -> list[dict]:
    entries = await db.audit_log.find(_query(**filters)).sort("seq", -1).skip(skip).limit(limit).to_list(None)
    return await _with_names(db, entries)


async def export_csv(db: AsyncDatabase, **filters) -> str:
    entries = await _with_names(db, await db.audit_log.find(_query(**filters)).sort("seq", 1).to_list(50_000))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["seq", "at_utc", "user", "email", "role", "action", "resource", "resource_id", "patient_id", "method", "path", "status", "ip", "details", "signature"])
    for e in entries:
        w.writerow([e["seq"], e["at"].isoformat(), e["actor_name"], e["actor_email"], e["actor_role"], e["action"], e["resource"],
                    e["resource_id"], e["patient_id"], e["method"], e["path"], e["status"], e["ip"], json.dumps(e["details"], default=str), e["sig"]])
    return out.getvalue()


async def verify(db: AsyncDatabase) -> dict:
    """Checks every entry's signature and that no sequence numbers are missing."""
    problems = []
    expected = 1
    checked = 0
    async for e in db.audit_log.find({}).sort("seq", 1):
        checked += 1
        if e["seq"] != expected:
            problems.append({"seq": expected, "issue": f"entries {expected}-{e['seq'] - 1} are missing"})
        if not hmac.compare_digest(e.get("sig", ""), _sign(e)):
            problems.append({"seq": e["seq"], "issue": "entry was changed after it was written"})
        expected = e["seq"] + 1
    last = await db.counters.find_one({"_id": "audit"})
    if last and last["seq"] >= expected:
        problems.append({"seq": expected, "issue": f"entries {expected}-{last['seq']} are missing"})
    return {"checked": checked, "ok": not problems, "problems": problems[:100]}


async def staff_activity(db: AsyncDatabase, *, date_from: date | None, date_to: date | None) -> list[dict]:
    pipeline = [
        {"$match": {**_query(date_from=date_from, date_to=date_to), "actor_role": {"$in": ["admin", "doctor", "receptionist"]}}},
        {"$group": {"_id": {"actor": "$actor_id", "action": "$action"}, "count": {"$sum": 1}, "last": {"$max": "$at"}}},
    ]
    rows: dict = {}
    async for r in await db.audit_log.aggregate(pipeline):
        a = rows.setdefault(r["_id"]["actor"], {"actor_id": r["_id"]["actor"], "counts": {}, "last_active": r["last"]})
        a["counts"][r["_id"]["action"]] = r["count"]
        a["last_active"] = max(a["last_active"], r["last"])
    users = {u["_id"]: u for u in await db.users.find({"_id": {"$in": list(rows)}}).to_list(None)}
    out = []
    for oid, a in rows.items():
        u = users.get(oid, {})
        out.append({**a, "actor_id": str(oid), "name": u.get("full_name"), "email": u.get("email"), "role": u.get("role")})
    return sorted(out, key=lambda a: a["last_active"], reverse=True)
