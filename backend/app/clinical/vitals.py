"""Vital-sign plausibility limits and abnormal-value flags (adults).

Paediatric norms depend on age, so for patients under 18 only temperature and
SpO2 are flagged. BMI uses the WHO Asian cut-offs (overweight from 23).
"""

# Values outside these are almost certainly typos and are rejected
PLAUSIBLE = {
    "bp_systolic": (50, 300),
    "bp_diastolic": (20, 200),
    "pulse": (20, 250),
    "temperature_c": (30.0, 45.0),
    "spo2": (50, 100),
    "weight_kg": (0.5, 400.0),
    "height_cm": (30.0, 250.0),
}

# (critical_low, low, high, critical_high); a value < low is "low", >= high is "high"
RANGES: dict[str, tuple[float | None, float | None, float | None, float | None]] = {
    "bp_systolic": (80, 90, 140, 180),
    "bp_diastolic": (50, 60, 90, 120),
    "pulse": (40, 60, 101, 131),
    "temperature_c": (35.0, 36.0, 38.0, 40.0),
    "spo2": (90, 95, None, None),
    "bmi": (None, 18.5, 23.0, None),
}

PAEDIATRIC_FLAGGED = {"temperature_c", "spo2"}

LABELS = {
    "bp_systolic": "Systolic BP",
    "bp_diastolic": "Diastolic BP",
    "pulse": "Pulse",
    "temperature_c": "Temperature",
    "spo2": "SpO2",
    "weight_kg": "Weight",
    "height_cm": "Height",
    "bmi": "BMI",
}

UNITS = {
    "bp_systolic": "mmHg",
    "bp_diastolic": "mmHg",
    "pulse": "bpm",
    "temperature_c": "°C",
    "spo2": "%",
    "weight_kg": "kg",
    "height_cm": "cm",
    "bmi": "kg/m²",
}


def compute_bmi(weight_kg: float | None, height_cm: float | None) -> float | None:
    if not weight_kg or not height_cm:
        return None
    return round(weight_kg / (height_cm / 100) ** 2, 1)


def flag(key: str, value: float | None) -> str | None:
    if value is None or key not in RANGES:
        return None
    crit_low, low, high, crit_high = RANGES[key]
    if crit_low is not None and value < crit_low:
        return "critical_low"
    if crit_high is not None and value >= crit_high:
        return "critical_high"
    if low is not None and value < low:
        return "low"
    if high is not None and value >= high:
        return "high"
    return None


def flag_all(values: dict[str, float | None], age: int | None) -> dict[str, str]:
    paediatric = age is not None and age < 18
    flags = {}
    for key, value in values.items():
        if paediatric and key not in PAEDIATRIC_FLAGGED:
            continue
        if f := flag(key, value):
            flags[key] = f
    return flags


def ranges_for(age: int | None) -> dict[str, dict]:
    """Normal ranges shown in charts (only those applied for this patient)."""
    paediatric = age is not None and age < 18
    return {
        key: {"low": r[1], "high": r[2]}
        for key, r in RANGES.items()
        if not paediatric or key in PAEDIATRIC_FLAGGED
    }
