"""Medicine master: seeded from a bundled starter list on first use, editable by admins."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pymongo.asynchronous.database import AsyncDatabase

SEED_FILE = Path(__file__).with_name("medicines_seed.json")

CLASS_LABELS = {
    "analgesic": "Analgesic / antipyretic", "nsaid": "NSAID", "antiplatelet": "Antiplatelet", "anticoagulant": "Anticoagulant",
    "penicillin": "Penicillin antibiotic", "macrolide": "Macrolide antibiotic", "cephalosporin": "Cephalosporin antibiotic",
    "fluoroquinolone": "Fluoroquinolone antibiotic", "tetracycline": "Tetracycline antibiotic", "nitroimidazole": "Nitroimidazole",
    "sulfonamide": "Sulfonamide", "urinary_antiseptic": "Urinary antiseptic", "azole_antifungal": "Azole antifungal",
    "anthelmintic": "Anthelmintic", "ppi": "Proton pump inhibitor", "h2_blocker": "H2 blocker", "prokinetic": "Prokinetic",
    "antiemetic": "Antiemetic", "antihistamine": "Antihistamine", "leukotriene_antagonist": "Leukotriene antagonist",
    "bronchodilator": "Bronchodilator", "biguanide": "Biguanide", "sulfonylurea": "Sulfonylurea", "dpp4_inhibitor": "DPP-4 inhibitor",
    "ccb": "Calcium channel blocker", "arb": "ARB", "acei": "ACE inhibitor", "beta_blocker": "Beta blocker", "thiazide": "Thiazide diuretic",
    "k_sparing_diuretic": "Potassium-sparing diuretic", "loop_diuretic": "Loop diuretic", "statin": "Statin", "thyroid": "Thyroid hormone",
    "corticosteroid": "Corticosteroid", "ssri": "SSRI antidepressant", "benzodiazepine": "Benzodiazepine", "opioid": "Opioid analgesic",
    "vitamin": "Vitamin", "rehydration": "Rehydration", "mineral": "Mineral supplement",
}


def norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9+ ]", " ", text.lower()).split())


async def ensure_seeded(db: AsyncDatabase) -> None:
    if await db.medicines.estimated_document_count():
        return
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))["medicines"]
    now = datetime.now(timezone.utc)
    await db.medicines.insert_many(
        [{**m, "search": norm(" ".join([m["generic"], *m["brands"]])), "source": "seed", "active": True, "created_at": now} for m in data]
    )


async def search(db: AsyncDatabase, q: str, limit: int = 15) -> list[dict]:
    """Match generic or brand names; results say which brand matched."""
    await ensure_seeded(db)
    words = norm(q).split()
    if not words:
        return []
    query = {"active": True, "$and": [{"search": {"$regex": rf"(^|\s){re.escape(w)}"}} for w in words]}
    found = await db.medicines.find(query).to_list(100)
    first = words[0]

    def rank(m):
        generic_hit = norm(m["generic"]).startswith(first)
        return (not generic_hit, len(m["generic"]))

    results = []
    for m in sorted(found, key=rank)[:limit]:
        brand = next((b for b in m["brands"] if norm(b).startswith(first)), None)
        results.append({**m, "matched_brand": brand})
    return results


async def match(db: AsyncDatabase, name: str | None, medicine_id=None) -> dict | None:
    """The master entry for a prescribed or currently-taken medicine (by id, generic or brand name)."""
    await ensure_seeded(db)
    if medicine_id:
        found = await db.medicines.find_one({"_id": medicine_id})
        if found:
            return found
    if not name:
        return None
    n = norm(name)
    for m in await db.medicines.find({"active": True}).to_list(None):
        names = [norm(m["generic"]), *(norm(b) for b in m["brands"])]
        if any(n == x or n.startswith(x + " ") or x.startswith(n + " ") for x in names):
            return m
    # single-word generic inside a longer name, e.g. "Tab Dolo 650" or "Paracetamol syrup"
    for m in await db.medicines.find({"active": True}).to_list(None):
        names = [norm(m["generic"]), *(norm(b) for b in m["brands"])]
        if any(re.search(rf"(^|\s){re.escape(x)}(\s|$)", n) for x in names if len(x) >= 4):
            return m
    return None
