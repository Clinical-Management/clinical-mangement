"""Deterministic lab-value handling: analyte names, reference ranges, flags and critical values.

The AI reads the report; these rules decide high/low/critical so a misread flag
can't hide a dangerous value. Critical thresholds are common adult defaults -
have them reviewed against your lab's own critical-value list.
"""

import re

# Canonical analyte keys -> names seen on Indian lab reports (lower-case, punctuation removed)
ALIASES = {
    "hba1c": ["hba1c", "hb a1c", "a1c", "glycated haemoglobin", "glycated hemoglobin", "glycosylated haemoglobin", "glycosylated hemoglobin"],
    "haemoglobin": ["haemoglobin", "hemoglobin", "hb", "hgb"],
    "potassium": ["potassium", "k", "serum potassium", "s potassium"],
    "sodium": ["sodium", "na", "serum sodium", "s sodium"],
    "glucose_fasting": ["fasting blood sugar", "fbs", "fasting glucose", "glucose fasting", "fasting plasma glucose", "blood sugar fasting"],
    "glucose_pp": ["post prandial blood sugar", "ppbs", "glucose pp", "post prandial glucose", "blood sugar pp"],
    "glucose_random": ["random blood sugar", "rbs", "random glucose", "glucose random", "blood glucose", "glucose"],
    "creatinine": ["creatinine", "serum creatinine", "s creatinine"],
    "urea": ["urea", "blood urea", "serum urea", "bun", "blood urea nitrogen"],
    "platelets": ["platelets", "platelet count", "plt"],
    "wbc": ["wbc", "wbc count", "total wbc count", "total leucocyte count", "total leukocyte count", "tlc", "white blood cells"],
    "tsh": ["tsh", "thyroid stimulating hormone"],
    "cholesterol_total": ["total cholesterol", "cholesterol", "serum cholesterol"],
    "ldl": ["ldl", "ldl cholesterol", "ldl c"],
    "hdl": ["hdl", "hdl cholesterol", "hdl c"],
    "triglycerides": ["triglycerides", "tg", "serum triglycerides"],
    "calcium": ["calcium", "serum calcium", "s calcium", "total calcium"],
    "inr": ["inr", "pt inr"],
    "alt": ["alt", "sgpt", "alanine aminotransferase"],
    "ast": ["ast", "sgot", "aspartate aminotransferase"],
    "bilirubin_total": ["total bilirubin", "bilirubin total", "bilirubin"],
}
_ALIAS_INDEX = {alias: key for key, aliases in ALIASES.items() for alias in aliases}


def normalise_name(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", name.lower().replace("₁", "1")).split())


def analyte_key(name: str) -> str:
    n = normalise_name(name)
    if n in _ALIAS_INDEX:
        return _ALIAS_INDEX[n]
    # "Serum Potassium (K+)" -> try without parenthesised/qualifier words
    stripped = normalise_name(re.sub(r"\(.*?\)", "", name))
    return _ALIAS_INDEX.get(stripped, stripped or n)


_NUMBER = r"(-?\d+(?:\.\d+)?)"


def parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    m = re.fullmatch(r"\s*[<>]?\s*" + _NUMBER + r"\s*", value.replace(",", ""))
    return float(m.group(1)) if m else None


def parse_range(text: str | None) -> tuple[float | None, float | None]:
    """'13.0 - 17.0' -> (13, 17); '< 5.7' / 'upto 5.7' -> (None, 5.7); '> 60' -> (60, None)."""
    if not text:
        return None, None
    t = text.replace(",", "").lower()
    if m := re.search(_NUMBER + r"\s*(?:-|–|to)\s*" + _NUMBER, t):
        return float(m.group(1)), float(m.group(2))
    if m := re.search(r"(?:<|<=|≤|upto|up to|less than)\s*" + _NUMBER, t):
        return None, float(m.group(1))
    if m := re.search(r"(?:>|>=|≥|more than|greater than)\s*" + _NUMBER, t):
        return float(m.group(1)), None
    return None, None


def _per_microlitre(value: float, unit: str) -> float | None:
    u = unit.lower().replace(" ", "")
    if "lakh" in u:
        return value * 100_000
    if any(k in u for k in ("10^3", "10³", "x10e3", "10*3", "k/ul", "thou", "10^9/l", "10e9/l")):
        return value * 1_000
    if any(k in u for k in ("/ul", "/µl", "/cumm", "/mm3", "cells/")):
        return value
    return None


def _normalised(key: str, value: float, unit: str) -> float | None:
    """Value in the unit the critical table uses, or None if the unit isn't understood."""
    u = unit.lower().replace(" ", "")
    if key in ("potassium", "sodium"):
        return value if u in ("mmol/l", "meq/l") else None
    if key.startswith("glucose"):
        if u == "mg/dl":
            return value
        if u == "mmol/l":
            return value * 18.0
        return None
    if key == "haemoglobin":
        return value if u == "g/dl" else value / 10 if u == "g/l" else None
    if key == "calcium":
        return value if u == "mg/dl" else None
    if key in ("platelets", "wbc"):
        return _per_microlitre(value, unit)
    if key == "inr":
        return value
    return None


# (critical_low, critical_high) in the units above
CRITICAL = {
    "potassium": (2.8, 6.2),
    "sodium": (120, 160),
    "glucose_fasting": (50, 400),
    "glucose_pp": (50, 400),
    "glucose_random": (50, 400),
    "haemoglobin": (7.0, 20.0),
    "calcium": (6.0, 13.0),
    "platelets": (20_000, 1_000_000),
    "wbc": (2_000, 30_000),
    "inr": (None, 5.0),
}


def evaluate(name: str, value: str | None, unit: str | None, reference_range: str | None,
             model_low: float | None = None, model_high: float | None = None) -> dict:
    """Deterministic interpretation of one result row."""
    key = analyte_key(name)
    number = parse_number(value)
    low, high = parse_range(reference_range)
    if low is None and high is None:
        low, high = model_low, model_high

    flag = None
    if number is not None:
        if low is not None and number < low:
            flag = "low"
        elif high is not None and number > high:
            flag = "high"
        elif low is not None or high is not None:
            flag = "normal"

    critical = False
    if number is not None and key in CRITICAL and unit:
        normal = _normalised(key, number, unit)
        if normal is not None:
            c_low, c_high = CRITICAL[key]
            if c_low is not None and normal < c_low:
                flag, critical = "critical_low", True
            elif c_high is not None and normal > c_high:
                flag, critical = "critical_high", True
    return {"analyte_key": key, "value_numeric": number, "ref_low": low, "ref_high": high, "flag": flag, "critical": critical}
