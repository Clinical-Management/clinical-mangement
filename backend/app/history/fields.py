"""Structured history fields and specialty templates.

Every field is free text in English (the doctor's working language); the
interview itself happens in the patient's language.
"""

from dataclasses import dataclass

LANGUAGES = ("en", "hi", "mr")

TEMPLATES = {
    "general_medicine": "General medicine",
    "paediatrics": "Paediatrics",
    "gynaecology": "Gynaecology",
}


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    section: str
    hint: str  # what the interviewer should capture
    stable: bool = False  # carried over for returning patients (confirm, don't re-ask)
    applies_to: str = "all"  # all | menstrual | children


FIELD_DEFS: tuple[FieldDef, ...] = (
    FieldDef("chief_complaint", "Chief complaint", "Presenting complaint", "Main problem in the patient's words"),
    FieldDef("onset", "Onset", "Presenting complaint", "When and how it started (sudden/gradual, trigger)"),
    FieldDef("duration", "Duration", "Presenting complaint", "How long it has lasted; constant or comes and goes"),
    FieldDef("severity", "Severity", "Presenting complaint", "Severity 0-10 and effect on daily activities"),
    FieldDef("associated_symptoms", "Associated symptoms", "Presenting complaint", "Other symptoms, including relevant negatives"),
    FieldDef("complaint_details", "Complaint-specific details", "Presenting complaint", "Template follow-up answers"),
    FieldDef("past_medical_history", "Past medical history", "Background", "Chronic illnesses, hospital stays", stable=True),
    FieldDef("past_surgical_history", "Past surgical history", "Background", "Operations with year", stable=True),
    FieldDef("current_medications", "Current medicines", "Background", "Name, dose, frequency, incl. supplements", stable=True),
    FieldDef("allergies", "Allergies", "Background", "Drug/food allergies and the reaction", stable=True),
    FieldDef("family_history", "Family history", "Background", "Illnesses in parents/siblings", stable=True),
    FieldDef("smoking", "Smoking / tobacco", "Lifestyle", "Smoking, chewing tobacco, gutkha; amount", stable=True),
    FieldDef("alcohol", "Alcohol", "Lifestyle", "Frequency and amount", stable=True),
    FieldDef("diet", "Diet", "Lifestyle", "Vegetarian or not, appetite, notable habits", stable=True),
    FieldDef("sleep", "Sleep", "Lifestyle", "Hours and quality of sleep"),
    FieldDef("menstrual_history", "Menstrual history", "Women's health", "LMP, cycle length/regularity, flow, pain", applies_to="menstrual"),
    FieldDef("obstetric_history", "Obstetric history", "Women's health", "Pregnancies, deliveries, miscarriages (G/P/A); currently pregnant?", stable=True, applies_to="menstrual"),
    FieldDef("vaccination_history", "Vaccination history", "Children", "Vaccines up to date per schedule; any missed", stable=True, applies_to="children"),
    FieldDef("changes_since_last_visit", "Changes since last visit", "Follow-up", "For returning patients: what changed since last time"),
)

FIELDS_BY_KEY = {f.key: f for f in FIELD_DEFS}
FIELD_KEYS = tuple(FIELDS_BY_KEY)


def select_template(specialization: str | None, age: int | None) -> str:
    spec = (specialization or "").lower()
    if any(k in spec for k in ("paed", "pediat", "child")):
        return "paediatrics"
    if any(k in spec for k in ("gyn", "obst")):
        return "gynaecology"
    if age is not None and age < 14:
        return "paediatrics"
    return "general_medicine"


def applicable_fields(*, template: str, age: int | None, gender: str | None, returning: bool) -> list[str]:
    menstrual = template == "gynaecology" or (gender == "female" and (age is None or 10 <= age <= 55))
    children = template == "paediatrics" or (age is not None and age < 18)
    keys = []
    for f in FIELD_DEFS:
        if f.applies_to == "menstrual" and not menstrual:
            continue
        if f.applies_to == "children" and not children:
            continue
        if f.key == "changes_since_last_visit" and not returning:
            continue
        keys.append(f.key)
    return keys
