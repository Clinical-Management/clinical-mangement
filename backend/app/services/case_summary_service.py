import difflib
import re
from datetime import datetime, timezone

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.ai.client import EngineError
from app.casesummary import sources as src
from app.casesummary.writer import rules_sections
from app.core.errors import Conflict, Invalid, NotFound
from app.services import patient_service

TITLES = dict(src.SECTIONS)
# The prescription already lists medicines, investigations, advice and follow-up
DEFAULT_EXCLUDED_FROM_PRINT = {"plan"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def word_diff(old: str, new: str) -> list[dict]:
    """Word-level diff as [{op: equal|insert|delete, text}] for highlighting what changed."""
    a, b = re.split(r"(\s+)", old or ""), re.split(r"(\s+)", new or "")
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            ops.append({"op": "equal", "text": "".join(a[i1:i2])})
        else:
            if i2 > i1:
                ops.append({"op": "delete", "text": "".join(a[i1:i2])})
            if j2 > j1:
                ops.append({"op": "insert", "text": "".join(b[j1:j2])})
    return ops


async def _write(db: AsyncDatabase, appt: dict, ctx: dict, writer_factory) -> tuple[dict, str, str | None]:
    """AI draft when the patient consented to AI processing and the AI is available; otherwise rules."""
    patient = await patient_service.get_patient(db, appt["patient_id"])
    if not patient["consent"].get("ai_processing"):
        return rules_sections(ctx), "rules", "Patient has not consented to AI processing"
    try:
        return await writer_factory().write(ctx), "ai", None
    except EngineError as exc:
        return rules_sections(ctx), "rules", f"AI unavailable ({exc}); built from the recorded data"


async def get_doc(db: AsyncDatabase, appt: dict) -> dict | None:
    return await db.case_summaries.find_one({"appointment_id": appt["_id"]})


async def view(db: AsyncDatabase, appt: dict, doc: dict | None) -> dict:
    if doc is None:
        raise NotFound("No case summary yet")
    current = await src.collect(db, appt)
    pending = src.describe_changes(doc["sources"], current["sources"])
    return {
        "appointment_id": str(appt["_id"]),
        "status": doc["status"],
        "sections": [
            {
                "key": key,
                "title": title,
                "text": doc["sections"][key],
                "edited": key in doc["edited_sections"],
                "suggestion": doc["suggestions"].get(key),
                "last_change": doc["diffs"].get(key),
            }
            for key, title in src.SECTIONS
        ],
        "stale": bool(pending),
        "pending_changes": pending,
        "last_regeneration_changes": doc["last_changes"],
        "generated_by": doc["generated_by"],
        "generation_note": doc.get("generation_note"),
        "generated_at": doc["generated_at"],
        "finalized_at": doc.get("finalized_at"),
        "finalized_by_role": doc.get("finalized_by_role"),
        "version": len(doc["versions"]) + 1,
        "updated_at": doc["updated_at"],
    }


async def generate(db: AsyncDatabase, appt: dict, writer_factory, actor: dict) -> dict:
    """First draft, or regeneration after new reports/notes. Sections the doctor edited keep
    the doctor's text; the new wording is offered as a suggestion instead."""
    collected = await src.collect(db, appt)
    fresh, generated_by, note = await _write(db, appt, collected["context"], writer_factory)
    fresh = {k: fresh[k].strip() for k in src.SECTION_KEYS}
    now = _now()
    doc = await get_doc(db, appt)

    if doc is None:
        doc = {
            "appointment_id": appt["_id"],
            "patient_id": appt["patient_id"],
            "status": "draft",
            "sections": fresh,
            "generated": fresh,
            "edited_sections": [],
            "suggestions": {},
            "diffs": {},
            "last_changes": [],
            "sources": collected["sources"],
            "generated_by": generated_by,
            "generation_note": note,
            "generated_at": now,
            "versions": [],
            "created_at": now,
            "updated_at": now,
        }
        await db.case_summaries.insert_one(doc)
        return doc

    changes = src.describe_changes(doc["sources"], collected["sources"]) or ["Regenerated on request"]
    sections, suggestions, diffs = dict(doc["sections"]), dict(doc["suggestions"]), {}
    for key in src.SECTION_KEYS:
        current, new = sections[key], fresh[key]
        if key in doc["edited_sections"]:
            if new != doc["generated"][key] and new != current:
                suggestions[key] = {"text": new, "diff": word_diff(current, new)}
        elif new != current:
            diffs[key] = word_diff(current, new)
            sections[key] = new
    version = {"at": now, "sections": doc["sections"], "status": doc["status"], "by_role": actor["role"], "reason": changes}
    return await db.case_summaries.find_one_and_update(
        {"_id": doc["_id"]},
        {
            "$set": {
                "sections": sections,
                "generated": fresh,
                "suggestions": suggestions,
                "diffs": diffs,
                "last_changes": changes,
                "sources": collected["sources"],
                "generated_by": generated_by,
                "generation_note": note,
                "generated_at": now,
                "updated_at": now,
                # new information reopens a finalized summary for review
                "status": "draft",
                "finalized_at": None,
            },
            "$push": {"versions": version},
        },
        return_document=ReturnDocument.AFTER,
    )


def _ensure_draft(doc: dict) -> None:
    if doc["status"] == "final":
        raise Conflict("The case summary is finalized. Reopen it to edit.")


async def save_sections(db: AsyncDatabase, doc: dict, edits: dict[str, str]) -> dict:
    """Doctor's free edits (autosaved)."""
    _ensure_draft(doc)
    unknown = set(edits) - set(src.SECTION_KEYS)
    if unknown:
        raise Invalid(f"Unknown sections: {', '.join(sorted(unknown))}")
    sections = {**doc["sections"], **{k: v for k, v in edits.items()}}
    edited = {k for k in src.SECTION_KEYS if sections[k].strip() != doc["generated"][k].strip()}
    return await db.case_summaries.find_one_and_update(
        {"_id": doc["_id"]},
        {"$set": {"sections": sections, "edited_sections": sorted(edited), "updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )


async def resolve_suggestion(db: AsyncDatabase, doc: dict, key: str, accept: bool) -> dict:
    _ensure_draft(doc)
    suggestion = doc["suggestions"].get(key)
    if not suggestion:
        raise NotFound("No suggestion for this section")
    update: dict = {"$unset": {f"suggestions.{key}": ""}, "$set": {"updated_at": _now()}}
    if accept:
        update["$set"].update({f"sections.{key}": suggestion["text"], f"diffs.{key}": suggestion["diff"]})
        update["$pull"] = {"edited_sections": key}
    return await db.case_summaries.find_one_and_update({"_id": doc["_id"]}, update, return_document=ReturnDocument.AFTER)


async def finalize(db: AsyncDatabase, doc: dict, actor: dict) -> dict:
    _ensure_draft(doc)
    if doc["suggestions"]:
        raise Conflict("Accept or dismiss the suggested updates before finalizing")
    now = _now()
    return await db.case_summaries.find_one_and_update(
        {"_id": doc["_id"]},
        {"$set": {"status": "final", "finalized_at": now, "finalized_by": actor["_id"], "finalized_by_role": actor["role"], "updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )


async def reopen(db: AsyncDatabase, doc: dict) -> dict:
    return await db.case_summaries.find_one_and_update(
        {"_id": doc["_id"]}, {"$set": {"status": "draft", "finalized_at": None, "updated_at": _now()}}, return_document=ReturnDocument.AFTER
    )


async def finalized_sections(db: AsyncDatabase, appt: dict, include: dict[str, bool] | None) -> list[dict]:
    """Sections of the finalized summary that the doctor chose to put in the prescription."""
    doc = await get_doc(db, appt)
    if not doc or doc["status"] != "final":
        return []
    include = include or {}
    return [
        {"key": k, "title": TITLES[k], "text": doc["sections"][k]}
        for k in src.SECTION_KEYS
        if include.get(k, k not in DEFAULT_EXCLUDED_FROM_PRINT) and doc["sections"][k].strip()
    ]
