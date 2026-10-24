from app.api.v1.routes.summaries import get_summary_engine_factory
from app.main import app
from tests.test_appointments import API as APPT, book, clinic, complete_visit, now  # noqa: F401
from tests.test_reports import pdf_bytes, upload
from tests.test_summaries import FakeEngine, lab, lab_result

FEES = {"new": 600, "follow_up": 0, "returning": 400}


def set_fees(client, c, fees=FEES):
    weekly = [{"weekday": d, "start": "09:00", "end": "10:00"} for d in range(6)]
    r = client.put(
        f"/api/v1/doctors/{c['doctor_id']}/schedule",
        json={"slot_minutes": 15, "follow_up_days": 7, "weekly": weekly, "fees": fees},
        headers=c["admin"],
    )
    assert r.status_code == 200, r.text


# --- prescription ------------------------------------------------------------


def test_prescription_autosave_and_allergy_warnings(client, clinic):
    pid = clinic["pid"]
    client.put(f"/api/v1/patients/{pid}/medical", json={"allergies": [{"substance": "Penicillin", "severity": "severe"}]}, headers=clinic["doctor"])
    appt = book(client, clinic).json()["id"]
    url = f"{APPT}/{appt}/prescription"

    empty = client.get(url, headers=clinic["doctor"]).json()
    assert empty["medicines"] == [] and empty["checks"] == [] and empty["status"] == "draft"

    body = {
        "medicines": [
            {"name": "Amoxicillin", "dose": "500 mg", "frequency": "1-0-1", "duration": "5 days"},
            {"name": "Paracetamol", "dose": "650 mg", "frequency": "SOS"},
        ],
        "investigations": [{"name": "CBC"}],
        "advice": "Plenty of fluids.",
        "follow_up": {"in_days": 5, "note": "Review with CBC"},
    }
    saved = client.put(url, json=body, headers=clinic["doctor"]).json()
    assert saved["follow_up"]["date"] == "2030-01-12"  # visit 2030-01-07 + 5 days
    allergy = [c for c in saved["checks"] if c["type"] == "allergy"]
    assert [(c["medicines"], c["severity"]) for c in allergy] == [(["Amoxicillin"], "high")]
    assert client.get(url, headers=clinic["doctor"]).json()["advice"] == "Plenty of fluids."

    assert client.put(url, json=body, headers=clinic["desk"]).status_code == 403  # receptionists don't prescribe


# --- notes autosave ----------------------------------------------------------


def test_notes_autosave_coalesces_change_log(client, clinic):
    appt = book(client, clinic).json()["id"]
    url = f"{APPT}/{appt}/notes"
    for text in ("Chest", "Chest clear", "Chest clear. No oedema."):
        r = client.patch(url, json={"examination": text}, headers=clinic["doctor"])
    notes = r.json()
    assert notes["examination"] == "Chest clear. No oedema."
    assert [c["change"] for c in notes["changes"]] == ["Examination findings updated"]

    notes = client.patch(url, json={"doctor_notes": "Anxious about results", "outcome": {"status": "improving"}}, headers=clinic["doctor"]).json()
    assert notes["doctor_notes"] == "Anxious about results" and notes["outcome"]["status"] == "improving"
    assert notes["changes"][-1]["change"] == "Doctor notes updated; Visit outcome updated"


# --- billing -----------------------------------------------------------------


# --- past visits & reports ---------------------------------------------------


def test_past_visits_and_report_summaries_in_list(client, clinic, now):
    first = book(client, clinic).json()["id"]
    client.post(f"{APPT}/{first}/notes/diagnoses", json={"code": "I10", "status": "final"}, headers=clinic["doctor"])
    client.put(f"{APPT}/{first}/prescription", json={"medicines": [{"name": "Amlodipine", "dose": "5 mg"}], "advice": "Low salt"}, headers=clinic["doctor"])
    client.patch(f"{APPT}/{first}/notes", json={"outcome": {"status": "improving", "note": "BP better"}}, headers=clinic["doctor"])
    complete_visit(client, clinic, first)

    second = book(client, clinic, day="2030-01-08").json()["id"]
    visits = client.get(f"/api/v1/patients/{clinic['pid']}/visits", params={"exclude": second}, headers=clinic["doctor"]).json()
    assert len(visits) == 1
    v = visits[0]
    assert v["diagnoses"][0]["code"] == "I10" and v["medicines"][0]["name"] == "Amlodipine" and v["outcome"]["note"] == "BP better"
    assert client.get(f"/api/v1/patients/{clinic['pid']}/visits", headers=clinic["desk"]).status_code == 403

    fake = FakeEngine([lab_result(lab("Serum Potassium", "6.8", "mmol/L", "3.5 - 5.1"), lab("HbA1c", "7.8", "%", "< 5.7"))])
    app.dependency_overrides[get_summary_engine_factory] = lambda: (lambda: fake)
    upload(client, clinic, pdf_bytes())
    reports = client.get(f"/api/v1/patients/{clinic['pid']}/reports", params={"include_summary": True}, headers=clinic["doctor"]).json()
    s = reports[0]["summary"]
    assert s["status"] == "ready" and s["abnormal_count"] == 2 and s["critical_values"]
    plain = client.get(f"/api/v1/patients/{clinic['pid']}/reports", params={"include_summary": True}, headers=clinic["desk"]).json()
    assert plain[0]["summary"] is None
