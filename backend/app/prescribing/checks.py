"""Prescription safety checks: allergy conflicts, drug interactions, duplicate therapy, dose range.

They prompt the doctor before finalizing; they do not replace clinical judgement or a full drug
database. Reference data lives in the medicine master and the rule tables below.
"""

import re

from pymongo.asynchronous.database import AsyncDatabase

from app.prescribing import medicines as med
from app.prescribing.medicines import CLASS_LABELS, norm

# Words in a recorded allergy -> drug classes it covers
ALLERGY_CLASSES = {
    "penicillin": "penicillin", "penicillins": "penicillin", "amoxicillin": "penicillin", "ampicillin": "penicillin",
    "sulfa": "sulfonamide", "sulpha": "sulfonamide", "sulfonamide": "sulfonamide", "sulphonamide": "sulfonamide",
    "nsaid": "nsaid", "nsaids": "nsaid", "ibuprofen": "nsaid", "diclofenac": "nsaid",
    "aspirin": "antiplatelet", "cephalosporin": "cephalosporin", "cephalosporins": "cephalosporin",
    "macrolide": "macrolide", "quinolone": "fluoroquinolone", "fluoroquinolone": "fluoroquinolone",
    "statin": "statin", "statins": "statin",
}
# allergy class -> other class with possible cross-reactivity
CROSS_REACTIVE = {"penicillin": "cephalosporin"}

# (side A, side B, severity, message); a side is "class:<class>" or "generic:<name>"
INTERACTIONS = [
    ("generic:warfarin", "class:nsaid", "high", "Bleeding risk: NSAIDs with warfarin"),
    ("generic:warfarin", "class:antiplatelet", "high", "Bleeding risk: antiplatelet with warfarin"),
    ("generic:warfarin", "class:azole_antifungal", "high", "Raises INR: fluconazole with warfarin"),
    ("generic:warfarin", "class:nitroimidazole", "high", "Raises INR: metronidazole with warfarin"),
    ("generic:warfarin", "class:sulfonamide", "high", "Raises INR: co-trimoxazole with warfarin"),
    ("generic:warfarin", "class:fluoroquinolone", "moderate", "May raise INR: fluoroquinolone with warfarin"),
    ("class:nsaid", "class:antiplatelet", "moderate", "GI bleeding risk: NSAID with antiplatelet"),
    ("class:acei", "class:arb", "high", "Dual RAS blockade (ACE inhibitor + ARB): hyperkalaemia, kidney injury"),
    ("class:acei", "class:k_sparing_diuretic", "high", "Hyperkalaemia risk: ACE inhibitor with spironolactone"),
    ("class:arb", "class:k_sparing_diuretic", "high", "Hyperkalaemia risk: ARB with spironolactone"),
    ("generic:clarithromycin", "class:statin", "high", "Myopathy risk: clarithromycin raises statin levels"),
    ("generic:clarithromycin", "generic:domperidone", "high", "QT prolongation: domperidone with clarithromycin"),
    ("class:macrolide", "class:fluoroquinolone", "moderate", "QT prolongation: macrolide with fluoroquinolone"),
    ("class:ssri", "generic:tramadol", "high", "Serotonin syndrome / seizure risk: SSRI with tramadol"),
    ("class:ssri", "class:nsaid", "moderate", "Bleeding risk: SSRI with NSAID"),
    ("class:benzodiazepine", "class:opioid", "high", "Respiratory depression: benzodiazepine with opioid"),
    ("generic:clopidogrel", "generic:omeprazole", "moderate", "Omeprazole may reduce clopidogrel's effect"),
    ("generic:clopidogrel", "generic:esomeprazole", "moderate", "Esomeprazole may reduce clopidogrel's effect"),
    ("class:sulfonylurea", "class:azole_antifungal", "moderate", "Hypoglycaemia risk: fluconazole with sulfonylurea"),
]

# Two medicines from the same class here is usually a mistake
DUPLICATE_CLASSES = {
    "nsaid", "ppi", "h2_blocker", "antihistamine", "statin", "acei", "arb", "beta_blocker", "ccb", "ssri",
    "benzodiazepine", "sulfonylurea", "penicillin", "macrolide", "cephalosporin", "fluoroquinolone", "biguanide",
}

_FREQ_WORDS = {
    "od": 1, "once daily": 1, "once a day": 1, "daily": 1, "hs": 1, "at night": 1, "once": 1,
    "bd": 2, "bid": 2, "twice daily": 2, "twice a day": 2,
    "tds": 3, "tid": 3, "thrice daily": 3, "three times a day": 3,
    "qid": 4, "four times a day": 4,
}


def doses_per_day(frequency: str | None) -> float | None:
    """'1-0-1' -> 2, 'TDS' -> 3. None for as-needed or non-daily schedules."""
    if not frequency:
        return None
    f = frequency.strip().lower().replace("½", "0.5")
    if re.fullmatch(r"\d+(\.\d+)?(\s*-\s*\d+(\.\d+)?){2,3}", f):
        return sum(float(x) for x in re.split(r"\s*-\s*", f))
    if any(w in f for w in ("sos", "prn", "as needed", "when required", "week", "month")):
        return None
    return _FREQ_WORDS.get(f)


def dose_mg(dose: str | None) -> float | None:
    """'500 mg' -> 500, '1 g' -> 1000, '50 mcg' -> 0.05. None for ml, puffs, IU etc."""
    if not dose:
        return None
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(mg|g|gm|mcg|µg)\s*", dose.lower())
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2)
    return value * {"mg": 1, "g": 1000, "gm": 1000, "mcg": 0.001, "µg": 0.001}[unit]


def _matches(side: str, entry: dict | None) -> bool:
    if not entry:
        return False
    kind, value = side.split(":", 1)
    return entry["class"] == value if kind == "class" else norm(entry["generic"]) == value


def _label(item: dict) -> str:
    return item["name"] + (" (current medicine)" if item.get("current") else "")


async def run_checks(
    db: AsyncDatabase, medicines: list[dict], *, allergies: list[str], current_meds: list[str], age: int | None, weight_kg: float | None
) -> list[dict]:
    items = []
    for m in medicines:
        entry = await med.match(db, m.get("generic") or m["name"], m.get("medicine_id"))
        if not entry and m.get("brand"):
            entry = await med.match(db, m["brand"])
        items.append({**m, "entry": entry})
    current = [{"name": name, "entry": await med.match(db, name), "current": True} for name in current_meds]
    warnings: list[dict] = []

    # Allergy conflicts
    for item in items:
        entry = item["entry"]
        names = {norm(item["name"])} | ({norm(entry["generic"]), *(norm(b) for b in entry["brands"])} if entry else set())
        for allergy in allergies:
            a = norm(allergy)
            words = set(a.split())
            if a in names or any(a in n.split() or n in words for n in names if len(n) >= 4):
                warnings.append({"type": "allergy", "severity": "high", "medicines": [item["name"]],
                                 "message": f"Patient is allergic to {allergy}"})
                continue
            classes = {ALLERGY_CLASSES[w] for w in words if w in ALLERGY_CLASSES}
            if entry and entry["class"] in classes:
                warnings.append({"type": "allergy", "severity": "high", "medicines": [item["name"]],
                                 "message": f"Allergy to {allergy}: {item['name']} is a {CLASS_LABELS.get(entry['class'], entry['class'])}"})
            elif entry and any(CROSS_REACTIVE.get(c) == entry["class"] for c in classes):
                warnings.append({"type": "allergy", "severity": "moderate", "medicines": [item["name"]],
                                 "message": f"Allergy to {allergy}: possible cross-reactivity with {item['name']}"})

    # Every prescribed medicine against each later one, and against what the patient already takes
    pairs = [(items[i], items[j]) for i in range(len(items)) for j in range(i + 1, len(items))]
    pairs += [(x, c) for x in items for c in current]

    # Interactions
    for x, y in pairs:
        for a, b, severity, message in INTERACTIONS:
            if (_matches(a, x["entry"]) and _matches(b, y["entry"])) or (_matches(b, x["entry"]) and _matches(a, y["entry"])):
                warnings.append({"type": "interaction", "severity": severity, "medicines": [_label(x), _label(y)], "message": message})

    # Duplicate therapy
    for x, y in pairs:
        ex, ey = x["entry"], y["entry"]
        same_drug = (ex and ey and ex["_id"] == ey["_id"]) or norm(x["name"]) == norm(y["name"])
        if same_drug:
            warnings.append({"type": "duplicate", "severity": "high" if not y.get("current") else "moderate",
                             "medicines": [_label(x), _label(y)],
                             "message": "Same medicine prescribed twice" if not y.get("current") else "Patient already takes this medicine"})
        elif ex and ey and ex["class"] == ey["class"] and ex["class"] in DUPLICATE_CLASSES:
            warnings.append({"type": "duplicate", "severity": "moderate", "medicines": [_label(x), _label(y)],
                             "message": f"Two {CLASS_LABELS.get(ex['class'], ex['class'])} medicines (duplicate therapy)"})

    # Dose range by age and weight
    child = age is not None and age < 18
    for item in items:
        entry, name = item["entry"], item["name"]
        if not entry:
            continue
        per_dose = dose_mg(item.get("dose"))
        per_day = doses_per_day(item.get("frequency"))
        daily = per_dose * per_day if per_dose is not None and per_day is not None else None
        limits = entry.get("child") if child else entry.get("adult")
        if child and not limits:
            if entry.get("adult"):
                warnings.append({"type": "dose", "severity": "info", "medicines": [name], "message": "No paediatric dose reference for this medicine; check the dose"})
            continue
        if not limits:
            continue
        if per_dose is None:
            if item.get("dose"):
                warnings.append({"type": "dose", "severity": "info", "medicines": [name], "message": f"Dose '{item['dose']}' could not be checked (use mg, g or mcg)"})
            continue
        if child:
            if not weight_kg:
                warnings.append({"type": "dose", "severity": "info", "medicines": [name], "message": "Weight not recorded: paediatric dose not checked"})
                continue
            if limits.get("max_mg_per_kg_dose") and per_dose / weight_kg > limits["max_mg_per_kg_dose"] * 1.05:
                warnings.append({"type": "dose", "severity": "high", "medicines": [name],
                                 "message": f"{per_dose:g} mg is {per_dose / weight_kg:.1f} mg/kg per dose; usual maximum {limits['max_mg_per_kg_dose']} mg/kg ({weight_kg:g} kg)"})
            if daily is not None and limits.get("max_mg_per_kg_day") and daily / weight_kg > limits["max_mg_per_kg_day"] * 1.05:
                warnings.append({"type": "dose", "severity": "high", "medicines": [name],
                                 "message": f"{daily:g} mg/day is {daily / weight_kg:.0f} mg/kg/day; usual maximum {limits['max_mg_per_kg_day']} mg/kg/day ({weight_kg:g} kg)"})
        elif limits.get("max_single_mg") and per_dose > limits["max_single_mg"]:
            warnings.append({"type": "dose", "severity": "high", "medicines": [name],
                             "message": f"{per_dose:g} mg per dose is above the usual maximum of {limits['max_single_mg']:g} mg"})
        if daily is not None and limits.get("max_daily_mg") and daily > limits["max_daily_mg"]:
            warnings.append({"type": "dose", "severity": "high", "medicines": [name],
                             "message": f"{daily:g} mg/day is above the usual maximum of {limits['max_daily_mg']:g} mg/day"})
    return warnings
