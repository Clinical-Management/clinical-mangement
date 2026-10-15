from app.clinical import icd10, vitals
from tests.test_appointments import API as APPT_API, book, clinic, now  # noqa: F401
from tests.test_patients import patient_payload

API = "/api/v1/appointments"


def visit(client, c, **kw):
    return book(client, c, **kw).json()["id"]


# --- pure helpers ------------------------------------------------------------


def test_flags_and_bmi():
    assert vitals.flag("bp_systolic", 120) is None
    assert vitals.flag("bp_systolic", 150) == "high"
    assert vitals.flag("bp_systolic", 185) == "critical_high"
    assert vitals.flag("spo2", 93) == "low" and vitals.flag("spo2", 88) == "critical_low"
    assert vitals.flag("pulse", 100) is None and vitals.flag("pulse", 101) == "high"
    assert vitals.compute_bmi(70, 170) == 24.2
    assert vitals.flag("bmi", 24.2) == "high"  # Asian cut-off: overweight from 23
    # children: only temperature and SpO2 are judged
    assert vitals.flag_all({"pulse": 130, "spo2": 92}, age=6) == {"spo2": "low"}


def test_icd10_search():
    assert icd10.search("E11.9")[0].code == "E11.9"
    assert icd10.search("e119")[0].code == "E11.9"
    assert icd10.search("hypertension")[0].code == "I10"
    assert icd10.lookup("i10").title == "Essential (primary) hypertension"


# --- vitals ------------------------------------------------------------------


def test_record_vitals_flags_and_alerts(client, clinic):
    appt = visit(client, clinic)
    r = client.post(
        f"{API}/{appt}/vitals",
        json={"bp_systolic": 150, "bp_diastolic": 95, "pulse": 88, "temperature": 101.3, "temperature_unit": "F",
              "spo2": 88, "weight_kg": 70, "height_cm": 170},
        headers=clinic["desk"],  # receptionist records at check-in
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["temperature_c"] == 38.5 and body["bmi"] == 24.2
    assert body["flags"] == {"bp_systolic": "high", "bp_diastolic": "high", "temperature_c": "high", "spo2": "critical_low", "bmi": "high"}

    alerts = client.get("/api/v1/alerts", headers=clinic["doctor"]).json()
    assert len(alerts) == 1 and "SpO2 88" in alerts[0]["message"]


def test_vitals_validation(client, clinic):
    appt = visit(client, clinic)
    url = f"{API}/{appt}/vitals"
    assert client.post(url, json={}, headers=clinic["desk"]).status_code == 422
    assert client.post(url, json={"bp_systolic": 80, "bp_diastolic": 120}, headers=clinic["desk"]).status_code == 422
    assert client.post(url, json={"bp_systolic": 120}, headers=clinic["desk"]).status_code == 422
    r = client.post(url, json={"pulse": 900}, headers=clinic["desk"])
    assert r.status_code == 422 and "re-check" in r.text


def test_vitals_trend_and_height_carried_forward(client, clinic):
    first = visit(client, clinic)
    client.post(f"{API}/{first}/vitals", json={"weight_kg": 80, "height_cm": 175}, headers=clinic["desk"])
    second = visit(client, clinic, day="2030-01-08")
    r = client.post(f"{API}/{second}/vitals", json={"weight_kg": 78}, headers=clinic["desk"])
    assert r.json()["bmi"] == 25.5 and r.json()["height_carried_forward"] is True

    trend = client.get(f"/api/v1/patients/{clinic['pid']}/vitals", headers=clinic["doctor"]).json()
    assert [v["weight_kg"] for v in trend["readings"]] == [80, 78]
    assert trend["ranges"]["spo2"] == {"low": 95, "high": None}
    # receptionists record vitals but don't browse the patient's history
    assert client.get(f"/api/v1/patients/{clinic['pid']}/vitals", headers=clinic["desk"]).status_code == 404


# --- examination & diagnoses -------------------------------------------------


def test_examination_and_diagnoses(client, clinic):
    appt = visit(client, clinic)
    base = f"{API}/{appt}/notes"
    r = client.put(f"{base}/examination", json={"text": "Chest clear. BP 150/95.", "dictated": True}, headers=clinic["doctor"])
    assert r.json()["examination"] == "Chest clear. BP 150/95."

    r = client.post(f"{base}/diagnoses", json={"code": "i10"}, headers=clinic["doctor"])
    diag = r.json()["diagnoses"][0]
    assert diag["code"] == "I10" and diag["status"] == "provisional"
    assert client.post(f"{base}/diagnoses", json={"code": "I10"}, headers=clinic["doctor"]).status_code == 409
    assert client.post(f"{base}/diagnoses", json={"code": "ZZZ"}, headers=clinic["doctor"]).status_code == 422

    r = client.patch(f"{base}/diagnoses/{diag['id']}", json={"status": "final"}, headers=clinic["doctor"])
    assert r.json()["diagnoses"][0]["status"] == "final"
    changes = [c["change"] for c in r.json()["changes"]]
    assert changes == [
        "Examination findings updated (dictated)",
        "Added provisional diagnosis I10 Essential (primary) hypertension",
        "Marked I10 final",
    ]
    r = client.delete(f"{base}/diagnoses/{diag['id']}", headers=clinic["doctor"])
    assert r.json()["diagnoses"] == []

    # receptionist has no access to clinical notes or ICD search
    assert client.get(base, headers=clinic["desk"]).status_code == 403
    assert client.get("/api/v1/icd10", params={"q": "fever"}, headers=clinic["desk"]).status_code == 403
    assert client.get("/api/v1/icd10", params={"q": "fever"}, headers=clinic["doctor"]).json()[0]["code"] == "R50.9"


def test_patient_sees_own_vitals_trend_only(client, clinic, make_user):
    owner = make_user("patient")
    pid = client.post("/api/v1/patients", json=patient_payload(relationship="self", phone="5556667777"), headers=owner).json()["patient_id"]
    assert client.get(f"/api/v1/patients/{pid}/vitals", headers=owner).status_code == 200
    assert client.get(f"/api/v1/patients/{clinic['pid']}/vitals", headers=owner).status_code == 404
