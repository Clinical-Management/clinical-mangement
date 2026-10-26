"""Create repeatable demo accounts, synthetic patients and a few months of clinic activity.

Run from backend/: python -m scripts.seed_demo [--no-staff-mfa]

Visits go through the normal services (booking, check-in, vitals, notes, prescriptions, billing), with the
clinic clock wound back for past days, so every screen shows data that the app itself could have produced.
Each run replaces the demo visits, so run it again on the morning of a demo to get a fresh queue for today.
"""

import argparse
import asyncio
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone

from app.core import clock
from app.core.config import settings
from app.core.security import hash_password
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_db
from app.schemas.appointment import AppointmentCreate, AppointmentStatus as S, WalkInCreate
from app.schemas.billing import BillIn, PaymentIn
from app.schemas.clinical import DiagnosisIn, VitalsIn
from app.schemas.patient import MedicalInfo, PatientCreate, PatientDemographics
from app.schemas.prescription import FinalizeIn, PrescriptionIn
from app.schemas.scheduling import DoctorScheduleIn
from app.schemas.user import Role
from app.services import (
    appointment_service,
    billing_service,
    case_summary_service,
    clinical_service,
    patient_service,
    prescription_service,
    reminder_service,
    scheduling_service,
)
from app.services.user_service import EmailAlreadyRegistered, create_user

DEMO_PASSWORD = "DemoPass123!"
DEMO_SEED = "clinical-management-demo-v1"

# key, email, full name, role
DEMO_USERS = (
    ("admin", "admin@demo.clinic", "Demo Admin", Role.ADMIN),
    ("gp", "doctor@demo.clinic", "Dr. Asha Rao", Role.DOCTOR),
    ("paeds", "pediatrician@demo.clinic", "Dr. Vikram Iyer", Role.DOCTOR),
    ("desk", "receptionist@demo.clinic", "Neha Kulkarni", Role.RECEPTIONIST),
    ("patient", "patient@demo.clinic", "Priya Deshmukh", Role.PATIENT),
)

CLINIC = {
    "name": "Sahyadri Family Clinic (Demo)",
    "address": "12 Demo Lane, Kothrud, Pune 411038",
    "phone": "+91 20 0000 0000",
    "email": "frontdesk@demo.clinic",
    "registration": "DEMO-CLINIC-0001",
    "upi_id": "democlinic@upi",
}

# Mon-Sat mornings and evenings, Sunday morning: any day the script runs has a clinic session
WEEKLY = [
    *({"weekday": d, "start": "09:00", "end": "13:00"} for d in range(6)),
    *({"weekday": d, "start": "17:00", "end": "20:00"} for d in range(6)),
    {"weekday": 6, "start": "10:00", "end": "13:00"},
]

DOCTORS = {
    "gp": {
        "schedule": {
            "specialization": "General Medicine",
            "fees": {"new": 600, "follow_up": 300, "returning": 500, "emergency": 1000, "teleconsultation": 400},
            "slot_minutes": 15,
            "follow_up_days": 7,
            "weekly": WEEKLY,
        },
        "credentials": {
            "registration_number": "DEMO-MMC-11111",
            "registration_council": "Maharashtra Medical Council",
            "qualifications": "MBBS, MD (General Medicine)",
        },
    },
    "paeds": {
        "schedule": {
            "specialization": "Paediatrics",
            "fees": {"new": 700, "follow_up": 350, "returning": 600, "emergency": 1200, "teleconsultation": 450},
            "slot_minutes": 20,
            "follow_up_days": 10,
            "weekly": WEEKLY,
        },
        "credentials": {
            "registration_number": "DEMO-MMC-22222",
            "registration_council": "Maharashtra Medical Council",
            "qualifications": "MBBS, DCH, MD (Paediatrics)",
        },
    },
}

HOME = {"line1": "Flat 4, Demo Residency", "city": "Pune", "state": "Maharashtra", "postal_code": "411038", "country": "India"}
APP_ONLY = {"language": "en", "channels": ["app"], "reminders": True}  # demo data never messages a real phone or inbox

# Profiles managed by the patient account (owner="patient") or registered at the front desk (owner=None)
DEMO_PROFILES = (
    {
        "key": "demo-patient-self",
        "owner": "patient",
        "full_name": "Priya Deshmukh",
        "date_of_birth": "1988-04-15",
        "gender": "female",
        "phone": "+91 90000 00101",
        "email": "patient@demo.clinic",
        "emergency_contact": {"name": "Rohan Deshmukh", "relationship": "Spouse", "phone": "+91 90000 00102"},
        "blood_group": "O+",
        "relationship": "self",
        "medical": {
            "allergies": [{"substance": "Pollen", "reaction": "Seasonal sneezing", "severity": "mild"}],
            "chronic_conditions": [{"name": "Allergic rhinitis", "since_year": 2018}],
            "current_medications": [],
        },
    },
    {
        "key": "demo-patient-child",
        "owner": "patient",
        "full_name": "Aarav Deshmukh",
        "date_of_birth": "2016-09-20",
        "gender": "male",
        "phone": "+91 90000 00101",
        "emergency_contact": {"name": "Priya Deshmukh", "relationship": "Mother", "phone": "+91 90000 00101"},
        "blood_group": "O+",
        "relationship": "child",
        "medical": {
            "allergies": [],
            "chronic_conditions": [{"name": "Mild intermittent asthma", "since_year": 2021}],
            "current_medications": [],
        },
    },
    {
        "key": "demo-patient-parent",
        "owner": "patient",
        "full_name": "Suresh Deshmukh",
        "date_of_birth": "1956-02-11",
        "gender": "male",
        "phone": "+91 90000 00103",
        "emergency_contact": {"name": "Priya Deshmukh", "relationship": "Daughter", "phone": "+91 90000 00101"},
        "blood_group": "A+",
        "relationship": "parent",
        "medical": {
            "allergies": [{"substance": "Sulfa drugs", "reaction": "Rash", "severity": "moderate"}],
            "chronic_conditions": [
                {"name": "Hypertension", "since_year": 2012},
                {"name": "Type 2 diabetes", "since_year": 2016},
            ],
            "current_medications": [
                {"name": "Telmisartan", "dosage": "40 mg", "frequency": "Once daily"},
                {"name": "Metformin", "dosage": "500 mg", "frequency": "Twice daily"},
            ],
        },
    },
    {
        "key": "demo-rahul",
        "owner": None,
        "full_name": "Rahul Mehta",
        "date_of_birth": "1979-07-03",
        "gender": "male",
        "phone": "+91 90000 00201",
        "blood_group": "B+",
        "medical": {
            "allergies": [],
            "chronic_conditions": [{"name": "Type 2 diabetes", "since_year": 2021}],
            "current_medications": [{"name": "Metformin", "dosage": "500 mg", "frequency": "Twice daily"}],
        },
    },
    {
        "key": "demo-fatima",
        "owner": None,
        "full_name": "Fatima Shaikh",
        "date_of_birth": "1992-12-08",
        "gender": "female",
        "phone": "+91 90000 00202",
        "blood_group": "AB+",
        "medical": {
            "allergies": [{"substance": "Penicillin", "reaction": "Hives and swelling", "severity": "severe"}],
            "chronic_conditions": [{"name": "Hypothyroidism", "since_year": 2019}],
            "current_medications": [{"name": "Levothyroxine", "dosage": "50 mcg", "frequency": "Once daily, empty stomach"}],
        },
    },
    {
        "key": "demo-anil",
        "owner": None,
        "full_name": "Anil Joshi",
        "date_of_birth": "1964-05-21",
        "gender": "male",
        "phone": "+91 90000 00203",
        "blood_group": "O-",
        "medical": {
            "allergies": [],
            "chronic_conditions": [{"name": "Hypertension", "since_year": 2015}],
            "current_medications": [{"name": "Amlodipine", "dosage": "5 mg", "frequency": "Once daily"}],
        },
    },
    {
        "key": "demo-sneha",
        "owner": None,
        "full_name": "Sneha Patil",
        "date_of_birth": "1999-01-30",
        "gender": "female",
        "phone": "+91 90000 00204",
        "blood_group": "B-",
        "medical": {"allergies": [], "chronic_conditions": [], "current_medications": []},
    },
    {
        "key": "demo-kavita",
        "owner": None,
        "full_name": "Kavita Nair",
        "date_of_birth": "1971-10-14",
        "gender": "female",
        "phone": "+91 90000 00205",
        "blood_group": "A-",
        "medical": {
            "allergies": [],
            "chronic_conditions": [{"name": "Osteoarthritis, both knees", "since_year": 2020}],
            "current_medications": [],
        },
    },
    {
        "key": "demo-meera",
        "owner": None,
        "full_name": "Meera Kulkarni",
        "date_of_birth": "2019-06-02",
        "gender": "female",
        "phone": "+91 90000 00206",
        "emergency_contact": {"name": "Sachin Kulkarni", "relationship": "Father", "phone": "+91 90000 00206"},
        "blood_group": "unknown",
        "medical": {"allergies": [], "chronic_conditions": [], "current_medications": []},
    },
)


def _med(name, generic, dose, frequency, duration, instructions=None, route="oral"):
    return {"name": name, "generic": generic, "dose": dose, "frequency": frequency, "duration": duration,
            "route": route, "instructions": instructions}


def _rx(medicines=(), investigations=(), advice="", diet="", follow_up_days=None, follow_up_note=None):
    return {
        "medicines": list(medicines),
        "investigations": [{"name": i} for i in investigations],
        "advice": advice,
        "diet_lifestyle": diet,
        "follow_up": {"in_days": follow_up_days, "note": follow_up_note} if follow_up_days else None,
    }


# Each visit runs through the real flow up to `status`. `day` is relative to today; `at` is the slot time.
# `pay` is "full", "partial" or None (left as a due); `booked_by` is "desk" (front desk), "patient" (online) or "walk_in".
VISITS = (
    # --- Rahul: diabetes reviews, giving a vitals trend --------------------------------------------------
    {
        "patient": "demo-rahul", "doctor": "gp", "day": -84, "at": "10:00", "booked_by": "walk_in", "status": "completed",
        "vitals": {"bp_systolic": 142, "bp_diastolic": 92, "pulse": 84, "weight_kg": 88.0, "height_cm": 172, "spo2": 98},
        "exam": "Fasting sugar (glucometer) 182 mg/dL. Mild acanthosis on the neck. Feet: sensation intact, pulses felt.",
        "diagnoses": [("E11.9", "final")],
        "rx": _rx(
            [_med("Glycomet 500", "Metformin", "500 mg", "1-0-1", "30 days", "after food")],
            ["HbA1c", "Lipid profile", "Serum creatinine"],
            advice="Check fasting sugar twice a week and keep a log.",
            diet="Cut sweets and sugary drinks; 30 minutes brisk walk daily.",
        ),
        "bill_items": [{"kind": "test", "description": "Glucometer sugar check", "unit_price": 10000}],
        "pay": "full", "mode": "cash", "outcome": "unchanged",
    },
    {
        "patient": "demo-rahul", "doctor": "gp", "day": -42, "at": "11:15", "booked_by": "desk", "status": "completed",
        "vitals": {"bp_systolic": 136, "bp_diastolic": 88, "pulse": 80, "weight_kg": 86.5, "spo2": 98},
        "exam": "HbA1c 8.1%. LDL 142 mg/dL. Creatinine normal. Weight down 1.5 kg.",
        "diagnoses": [("E11.9", "final"), ("E78.5", "final")],
        "rx": _rx(
            [
                _med("Glycomet 500", "Metformin", "500 mg", "1-0-1", "30 days", "after food"),
                _med("Atorva 10", "Atorvastatin", "10 mg", "0-0-1", "30 days", "at night"),
            ],
            advice="Continue sugar log. Repeat HbA1c in 3 months.",
            diet="Low-fat diet; continue walking.",
        ),
        "pay": "full", "mode": "upi", "reference": "UPI-DEMO-4242", "outcome": "improving",
    },
    {"patient": "demo-rahul", "doctor": "gp", "day": 0, "at": "09:30", "booked_by": "walk_in", "status": "waiting",
     "vitals": {"bp_systolic": 130, "bp_diastolic": 84, "pulse": 78, "weight_kg": 85.2, "spo2": 99}},

    # --- Suresh (patient account's parent): BP/diabetes review, auto-booked follow-up, medicine reminders ---
    {
        "patient": "demo-patient-parent", "doctor": "gp", "day": -60, "at": "10:30", "booked_by": "patient", "status": "completed",
        "vitals": {"bp_systolic": 158, "bp_diastolic": 96, "pulse": 76, "weight_kg": 74.0, "height_cm": 168, "spo2": 97},
        "exam": "BP high on two readings. No pedal oedema. Heart sounds normal.",
        "diagnoses": [("I10", "final"), ("E11.9", "final")],
        "rx": _rx(
            [
                _med("Telma 40", "Telmisartan", "40 mg", "1-0-0", "30 days"),
                _med("Amlong 5", "Amlodipine", "5 mg", "0-0-1", "30 days"),
                _med("Glycomet 500", "Metformin", "500 mg", "1-0-1", "30 days", "after food"),
            ],
            ["HbA1c", "Urine microalbumin"],
            advice="Home BP log morning and evening.",
            diet="Salt under 5 g a day.",
        ),
        "concession": {"type": "senior"}, "pay": "full", "mode": "card", "reference": "CARD-DEMO-0042", "outcome": "unchanged",
    },
    {
        "patient": "demo-patient-parent", "doctor": "gp", "day": -28, "at": "10:45", "booked_by": "patient", "status": "completed",
        "vitals": {"bp_systolic": 138, "bp_diastolic": 86, "pulse": 74, "weight_kg": 73.2, "spo2": 98},
        "exam": "Home BP log mostly 130-140/80-88. HbA1c 7.2%. Microalbumin normal.",
        "diagnoses": [("I10", "final"), ("E11.9", "final")],
        "rx": _rx(
            [
                _med("Telma 40", "Telmisartan", "40 mg", "1-0-0", "30 days"),
                _med("Amlong 5", "Amlodipine", "5 mg", "0-0-1", "30 days"),
                _med("Glycomet 500", "Metformin", "500 mg", "1-0-1", "30 days", "after food"),
            ],
            advice="Continue the BP log.",
            follow_up_days=33, follow_up_note="BP and sugar review",
        ),
        "concession": {"type": "senior"}, "pay": "full", "mode": "upi", "reference": "UPI-DEMO-7781", "outcome": "improving",
        "medicine_reminders": True,
    },

    # --- Priya (the patient account) and her son Aarav ------------------------------------------------------
    {
        "patient": "demo-patient-self", "doctor": "gp", "day": -35, "at": "18:00", "booked_by": "patient", "status": "completed",
        "vitals": {"bp_systolic": 112, "bp_diastolic": 72, "pulse": 72, "temperature": 98.4, "temperature_unit": "F", "weight_kg": 58.0, "height_cm": 160},
        "exam": "Nasal mucosa pale and boggy. Clear rhinorrhoea. Chest clear.",
        "diagnoses": [("J30.9", "final")],
        "rx": _rx(
            [
                _med("Levocet", "Levocetirizine", "5 mg", "0-0-1", "10 days", "at night"),
                _med("Montair 10", "Montelukast", "10 mg", "0-0-1", "10 days", "at night"),
            ],
            advice="Avoid dust and pollen exposure; steam inhalation twice a day.",
        ),
        "pay": "full", "mode": "upi", "reference": "UPI-DEMO-1188", "outcome": "resolved",
    },
    {
        "patient": "demo-patient-child", "doctor": "paeds", "day": -14, "at": "11:00", "booked_by": "patient", "status": "completed",
        "vitals": {"pulse": 102, "temperature": 38.4, "spo2": 96, "weight_kg": 30.5, "height_cm": 136},
        "exam": "Febrile, throat congested, mild wheeze on both sides. No chest retractions.",
        "diagnoses": [("J06.9", "final"), ("J45.909", "provisional")],
        "rx": _rx(
            [
                _med("Crocin 250", "Paracetamol", "250 mg", "SOS", "3 days", "if fever above 100 F"),
                _med("Asthalin inhaler", "Salbutamol", "2 puffs", "TDS", "5 days", "with spacer", route="inhaled"),
            ],
            advice="Plenty of fluids. Return at once if breathing becomes difficult.",
        ),
        "bill_items": [{"kind": "procedure", "description": "Nebulisation", "unit_price": 25000}],
        "pay": "full", "mode": "cash", "outcome": "improving",
    },
    {"patient": "demo-patient-self", "doctor": "gp", "day": 3, "at": "18:30", "booked_by": "patient", "status": "scheduled"},

    # --- Fatima: thyroid review with a penicillin allergy on record -----------------------------------------
    {
        "patient": "demo-fatima", "doctor": "gp", "day": -21, "at": "12:00", "booked_by": "desk", "status": "completed",
        "vitals": {"bp_systolic": 118, "bp_diastolic": 76, "pulse": 68, "weight_kg": 64.5, "height_cm": 158, "spo2": 99},
        "exam": "TSH 7.8 on current dose. Feels tired. No goitre.",
        "diagnoses": [("E03.9", "final")],
        "rx": _rx(
            [_med("Thyronorm 75", "Levothyroxine", "75 mcg", "1-0-0", "6 weeks", "empty stomach, 30 min before breakfast")],
            ["TSH"],
            advice="Repeat TSH after 6 weeks on the new dose.",
            follow_up_days=45, follow_up_note="Review with TSH report",
        ),
        "pay": "full", "mode": "upi", "reference": "UPI-DEMO-3310", "outcome": "unchanged",
    },

    # --- Kavita: knee pain, part paid ----------------------------------------------------------------------
    {
        "patient": "demo-kavita", "doctor": "gp", "day": -9, "at": "17:30", "booked_by": "desk", "status": "completed",
        "vitals": {"bp_systolic": 128, "bp_diastolic": 82, "pulse": 76, "weight_kg": 71.0, "height_cm": 155},
        "exam": "Crepitus both knees, no effusion. Range of movement mildly reduced.",
        "diagnoses": [("M19.90", "final")],
        "rx": _rx(
            [
                _med("Hifenac", "Aceclofenac", "100 mg", "1-0-1", "5 days", "after food"),
                _med("Pan 40", "Pantoprazole", "40 mg", "1-0-0", "5 days", "before breakfast"),
                _med("Uprise-D3 60K", "Cholecalciferol", "60000 IU", "once weekly", "8 weeks"),
            ],
            ["X-ray both knees (standing)", "Vitamin D"],
            advice="Quadriceps strengthening exercises daily.",
            diet="Weight reduction will ease knee pain.",
        ),
        "pay": "partial", "mode": "cash", "outcome": "improving",
    },

    # --- Sneha: a missed and a cancelled booking ------------------------------------------------------------
    {"patient": "demo-sneha", "doctor": "gp", "day": -5, "at": "12:30", "booked_by": "desk", "status": "no_show"},
    {"patient": "demo-sneha", "doctor": "gp", "day": 6, "at": "11:00", "booked_by": "desk", "status": "cancelled",
     "cancel_reason": "Patient travelling"},

    # --- Today's queue --------------------------------------------------------------------------------------
    {
        "patient": "demo-anil", "doctor": "gp", "day": 0, "at": "09:00", "booked_by": "desk", "status": "completed",
        "vitals": {"bp_systolic": 150, "bp_diastolic": 94, "pulse": 82, "weight_kg": 79.0, "height_cm": 170, "spo2": 98},
        "exam": "BP above target on amlodipine 5 mg. No headache or chest pain.",
        "diagnoses": [("I10", "final")],
        "rx": _rx(
            [_med("Amlong 10", "Amlodipine", "10 mg", "1-0-0", "30 days")],
            ["ECG", "Serum electrolytes"],
            advice="Home BP log; reduce salt.",
        ),
        "pay": None, "outcome": "unchanged",  # left unpaid: shows on the dues list
    },
    {
        "patient": "demo-meera", "doctor": "paeds", "day": 0, "at": "09:20", "booked_by": "walk_in", "status": "in_consultation",
        "vitals": {"pulse": 110, "temperature": 38.9, "spo2": 98, "weight_kg": 20.0, "height_cm": 112},
    },
    {"patient": "demo-sneha", "doctor": "gp", "day": 0, "at": "09:45", "booked_by": "walk_in", "status": "waiting"},
    {"patient": "demo-kavita", "doctor": "gp", "day": 0, "at": "19:00", "booked_by": "desk", "status": "scheduled"},

    # --- Coming up ------------------------------------------------------------------------------------------
    {"patient": "demo-fatima", "doctor": "paeds", "day": 2, "at": "10:00", "booked_by": "desk", "status": "scheduled"},
    {"patient": "demo-patient-child", "doctor": "paeds", "day": 8, "at": "17:20", "booked_by": "patient", "status": "scheduled"},
    {"patient": "demo-rahul", "doctor": "gp", "day": 12, "at": "10:15", "booked_by": "desk", "status": "scheduled"},
)

# Time sources replaced while a past day is replayed (billing, reminders and scheduling read clock.clinic_now)
TIME_SOURCES = (appointment_service, case_summary_service, clinical_service, patient_service, prescription_service)

# Visit data removed and rebuilt on each run, matched by the demo patients' ids or their appointments
VISIT_COLLECTIONS = (
    "bills", "receipts", "receipt_deliveries", "prescriptions", "prescription_versions", "rx_deliveries", "rx_links",
    "clinical_notes", "vitals", "notifications", "case_summaries", "history_sessions", "callbacks", "alerts", "appointments",
)


@contextmanager
def clinic_time(day: date):
    """Run the services as if it were `day` in the clinic; the yielded `at(hhmm, minutes)` moves the clock."""
    state = {"now": clock.clinic_now()}

    def at(hhmm: str, minutes: int = 0) -> None:
        h, m = map(int, hhmm.split(":"))
        state["now"] = datetime.combine(day, time(h, m), tzinfo=clock.clinic_tz()) + timedelta(minutes=minutes)

    saved = clock.clinic_now, {m: m._now for m in TIME_SOURCES}
    clock.clinic_now = lambda: state["now"]
    for module in TIME_SOURCES:
        module._now = lambda: state["now"].astimezone(timezone.utc)
    try:
        yield at
    finally:
        clock.clinic_now = saved[0]
        for module, fn in saved[1].items():
            module._now = fn


async def _seed_user(db, email: str, full_name: str, role: Role) -> dict:
    user = await db.users.find_one({"email": email})
    if user:
        if user.get("demo_seed") != DEMO_SEED:
            raise RuntimeError(f"Refusing to change existing non-demo account {email}")
        await db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "full_name": full_name,
                    "password_hash": hash_password(DEMO_PASSWORD),
                    "role": role.value,
                    "is_active": True,
                },
                "$unset": {"failed_logins": "", "locked_until": ""},
            },
        )
        return await db.users.find_one({"_id": user["_id"]})

    try:
        user = await create_user(db, email=email, full_name=full_name, password=DEMO_PASSWORD, role=role)
    except EmailAlreadyRegistered as exc:
        raise RuntimeError(f"Email {email} was registered while seeding demo data; retry the command") from exc
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"demo_seed": DEMO_SEED}})
    user["demo_seed"] = DEMO_SEED
    return user


async def _seed_clinic(db, users: dict) -> None:
    # Only fills a blank clinic profile: an admin's own settings are kept
    await db.settings.update_one({"_id": "clinic"}, {"$setOnInsert": CLINIC}, upsert=True)
    for key, setup in DOCTORS.items():
        doctor_id = str(users[key]["_id"])
        await scheduling_service.save_schedule(db, doctor_id, DoctorScheduleIn.model_validate(setup["schedule"]))
        await db.doctor_profiles.update_one({"_id": users[key]["_id"]}, {"$set": setup["credentials"]})

    today = clock.clinic_today()
    await db.holidays.delete_many({"demo_seed": DEMO_SEED})
    await db.doctor_leaves.delete_many({"demo_seed": DEMO_SEED})
    await db.holidays.insert_one({"date": (today + timedelta(days=20)).isoformat(), "name": "Clinic closed (demo holiday)", "demo_seed": DEMO_SEED})
    await db.doctor_leaves.insert_one({
        "doctor_id": users["paeds"]["_id"], "start_date": (today + timedelta(days=15)).isoformat(),
        "end_date": (today + timedelta(days=17)).isoformat(), "reason": "Conference (demo)",
        "created_at": datetime.now(timezone.utc), "demo_seed": DEMO_SEED,
    })


async def _seed_patient(db, users: dict, profile: dict) -> dict:
    owner = users.get(profile["owner"]) if profile["owner"] else None
    fields = {key: value for key, value in profile.items() if key not in {"key", "owner", "medical"}}
    fields.setdefault("address", HOME)
    demographics = {**fields, "communication": APP_ONLY}

    patient = await db.patients.find_one({"demo_seed": profile["key"]})
    if patient:
        await patient_service.update_demographics(db, patient["patient_id"], PatientDemographics.model_validate(demographics))
    else:
        body = PatientCreate.model_validate({
            **demographics,
            "consent": {"data_storage": True, "voice_recording": False, "ai_processing": False},
            "allow_duplicate": True,
        })
        patient = await patient_service.create_patient(
            db, body, actor=owner or users["desk"], managed_by=owner["_id"] if owner else None
        )
        await db.patients.update_one({"_id": patient["_id"]}, {"$set": {"demo_seed": profile["key"]}})

    await patient_service.update_medical(db, patient["patient_id"], MedicalInfo.model_validate(profile["medical"]), actor=users["gp"])
    return await patient_service.get_patient(db, patient["patient_id"])


async def _clear_visits(db, patient_ids: list[str], doctor_ids: list) -> None:
    appointment_ids = await db.appointments.distinct("_id", {"patient_id": {"$in": patient_ids}})
    for name in VISIT_COLLECTIONS:
        await db[name].delete_many({"$or": [{"patient_id": {"$in": patient_ids}}, {"appointment_id": {"$in": appointment_ids}}]})
    for doctor_id in doctor_ids:
        await db.counters.delete_many({"_id": {"$regex": f"^token:{doctor_id}:"}})


async def _bill(db, appt: dict, visit: dict, users: dict) -> None:
    desk = users["desk"]
    if visit.get("bill_items") or visit.get("concession"):
        await billing_service.save_bill(db, appt, BillIn.model_validate({
            "items": visit.get("bill_items", []), "concession": visit.get("concession", {"type": "none"}),
        }), desk)
    view = await billing_service.get_bill(db, appt)
    if visit.get("pay") and view["balance"]:
        amount = view["balance"] if visit["pay"] == "full" else view["balance"] // 200 * 100  # about half, in whole rupees
        await billing_service.pay(db, appt, PaymentIn(mode=visit["mode"], amount=amount, reference=visit.get("reference")), desk)


async def _consult(db, appt: dict, visit: dict, doctor: dict, at) -> dict:
    at(visit["at"], 2)
    appt = await appointment_service.set_status(db, appt, S.IN_CONSULTATION, doctor)
    if exam := visit.get("exam"):
        at(visit["at"], 5)
        await clinical_service.save_examination(db, appt, exam, False, doctor)
    for code, status in visit.get("diagnoses", []):
        await clinical_service.add_diagnosis(db, appt, DiagnosisIn(code=code, status=status), doctor)
    if rx := visit.get("rx"):
        at(visit["at"], 9)
        await prescription_service.save(db, appt, PrescriptionIn.model_validate(rx), doctor)
        await prescription_service.finalize(db, appt, FinalizeIn(acknowledged=True), doctor)
    if outcome := visit.get("outcome"):
        await clinical_service.save_fields(db, appt, {"outcome": {"status": outcome}}, doctor)
    return appt


async def _visit(db, visit: dict, users: dict, patients: dict) -> dict:
    patient = patients[visit["patient"]]
    doctor = users[visit["doctor"]]
    desk = users["desk"]
    day = clock.clinic_today() + timedelta(days=visit["day"])

    with clinic_time(min(day, clock.clinic_today())) as at:
        if visit["day"] <= 0:
            at("07:30")
        if visit["booked_by"] == "walk_in":
            at(visit["at"], -5)
            appt = await appointment_service.walk_in(db, WalkInCreate(patient_id=patient["patient_id"], doctor_id=str(doctor["_id"])), desk)
        else:
            booker = users["patient"] if visit["booked_by"] == "patient" else desk
            appt = await appointment_service.book(db, AppointmentCreate(
                patient_id=patient["patient_id"], doctor_id=str(doctor["_id"]), date=day, start_time=visit["at"],
            ), booker)

        status = visit["status"]
        if status == "cancelled":
            return await appointment_service.cancel(db, appt, visit.get("cancel_reason"), desk)
        if status == "no_show":
            at(visit["at"], 30)
            return await appointment_service.set_status(db, appt, S.NO_SHOW, desk)
        if status == "scheduled":
            return appt

        if appt["status"] == S.SCHEDULED.value:
            at(visit["at"], -10)
            appt = await appointment_service.check_in(db, appt, desk)
        if vitals := visit.get("vitals"):
            at(visit["at"], -5)
            await clinical_service.record_vitals(db, appt, VitalsIn.model_validate(vitals), desk)
        if status == "waiting":
            return appt

        appt = await _consult(db, appt, visit, doctor, at)
        if status == "in_consultation":
            return appt

        at(visit["at"], 14)
        appt = await appointment_service.set_status(db, appt, S.COMPLETED, doctor)
        at(visit["at"], 18)
        await _bill(db, appt, visit, users)
        return appt


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-staff-mfa", action="store_true",
                        help="turn off the staff authenticator-app requirement so demo staff sign in with a password only")
    args = parser.parse_args()

    if settings.app_env.lower() in {"production", "prod"}:
        raise RuntimeError("Demo data seeding is disabled in production")

    await connect_to_mongo()
    try:
        db = get_db()
        users = {}
        for key, email, full_name, role in DEMO_USERS:
            users[key] = await _seed_user(db, email, full_name, role)
        await _seed_clinic(db, users)
        if args.no_staff_mfa:
            await db.settings.update_one({"_id": "security"}, {"$set": {"staff_mfa_required": False}}, upsert=True)

        patients = {profile["key"]: await _seed_patient(db, users, profile) for profile in DEMO_PROFILES}
        await _clear_visits(db, [p["patient_id"] for p in patients.values()], [users["gp"]["_id"], users["paeds"]["_id"]])

        for visit in sorted(VISITS, key=lambda v: (v["day"], v["at"])):
            appt = await _visit(db, visit, users, patients)
            if visit.get("medicine_reminders"):
                version = await db.prescription_versions.find_one({"appointment_id": appt["_id"]}, sort=[("version", -1)])
                await reminder_service.schedule_medicine_reminders(db, version, users["gp"])

        print(f"Demo accounts (password for each: {DEMO_PASSWORD})")
        for _, email, full_name, role in DEMO_USERS:
            print(f"  {role.value:12} {email:28} {full_name}")
        print(f"Seeded {len(patients)} patients and {len(VISITS)} visits, including today's queue.")
        print("The patient account manages Priya (self), Aarav (child) and Suresh (parent).")
        if not args.no_staff_mfa:
            print("Staff accounts will be prompted to set up MFA on first sign-in when required (see --no-staff-mfa).")
        print("All patient information is synthetic demo data; messages go to the in-app inbox only.")
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
