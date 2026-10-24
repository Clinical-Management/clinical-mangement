from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core import clock
from app.core.config import settings
from tests.test_patients import patient_payload

API = "/api/v1/appointments"
MONDAY = "2030-01-07"
TUESDAY = "2030-01-08"


@pytest.fixture
def now(monkeypatch):
    """Freeze the clinic clock; returns a setter to move it."""

    def set_now(iso: str):
        fixed = datetime.fromisoformat(iso).replace(tzinfo=ZoneInfo(settings.clinic_timezone))
        monkeypatch.setattr(clock, "clinic_now", lambda: fixed)

    set_now(f"{MONDAY}T08:00")
    return set_now


@pytest.fixture
def clinic(client, make_user, now):
    """Admin, receptionist, one doctor working Mon-Sat 09:00-10:00 (15 min slots) and one patient."""
    admin, desk = make_user("admin"), make_user("receptionist")
    r = client.post(
        "/api/v1/admin/users",
        json={"email": "doc@clinic.com", "full_name": "Dr Mehta", "password": "password123", "role": "doctor"},
        headers=admin,
    )
    doctor_id = r.json()["id"]
    weekly = [{"weekday": d, "start": "09:00", "end": "10:00"} for d in range(6)]
    r = client.put(
        f"/api/v1/doctors/{doctor_id}/schedule",
        json={"slot_minutes": 15, "follow_up_days": 7, "weekly": weekly},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    doctor_token = client.post("/api/v1/auth/login", json={"email": "doc@clinic.com", "password": "password123"})
    doctor = {"Authorization": f"Bearer {doctor_token.json()['access_token']}"}
    pid = client.post("/api/v1/patients", json=patient_payload(), headers=desk).json()["patient_id"]
    return {"admin": admin, "desk": desk, "doctor": doctor, "doctor_id": doctor_id, "pid": pid}


def book(client, c, day=MONDAY, time="09:00", headers=None, pid=None):
    return client.post(
        API,
        json={"patient_id": pid or c["pid"], "doctor_id": c["doctor_id"], "date": day, "start_time": time},
        headers=headers or c["desk"],
    )


def slots(client, c, day=MONDAY):
    return client.get(f"/api/v1/doctors/{c['doctor_id']}/slots", params={"date": day}, headers=c["desk"]).json()


def complete_visit(client, c, appt_id, paid=True):
    assert client.post(f"{API}/{appt_id}/check-in", headers=c["desk"]).status_code == 200
    for s in ("in_consultation", "completed"):
        assert client.post(f"{API}/{appt_id}/status", json={"status": s}, headers=c["doctor"]).status_code == 200
    if paid:
        pay_visit(client, c, appt_id)


def pay_visit(client, c, appt_id, amount=50000):
    """Pays the visit in full through its bill (a custom fee if the doctor has none set)."""
    bill = client.get(f"{API}/{appt_id}/bill", headers=c["desk"]).json()
    if bill["fee_missing"]:
        bill = client.put(f"{API}/{appt_id}/bill", json={"fee": {"basis": "custom", "amount": amount, "reason": "test fee"}}, headers=c["desk"]).json()
    r = client.post(f"{API}/{appt_id}/bill/payments", json={"mode": "cash", "amount": bill["balance"]}, headers=c["desk"])
    assert r.status_code == 200, r.text


# --- availability ------------------------------------------------------------


def test_slots_follow_schedule_and_bookings(client, clinic):
    day = slots(client, clinic)
    assert day["bookable"] and [s["start"] for s in day["slots"]] == ["09:00", "09:15", "09:30", "09:45"]
    book(client, clinic, time="09:15")
    assert [s["status"] for s in slots(client, clinic)["slots"]] == ["available", "booked", "available", "available"]

    sunday = slots(client, clinic, "2030-01-13")
    assert sunday["bookable"] is False and "not available" in sunday["reason"]


def test_past_slots_cannot_be_booked(client, clinic, now):
    now(f"{MONDAY}T09:20")
    assert [s["status"] for s in slots(client, clinic)["slots"]][:2] == ["past", "past"]
    assert book(client, clinic, time="09:00").status_code == 422
    assert book(client, clinic, time="09:30").status_code == 201


def test_holiday_and_leave_block_booking_and_report_conflicts(client, clinic):
    booked = book(client, clinic, day=TUESDAY).json()
    r = client.post("/api/v1/holidays", json={"date": TUESDAY, "name": "Founders Day"}, headers=clinic["admin"])
    assert r.status_code == 201
    assert [a["id"] for a in r.json()["conflicting_appointments"]] == [booked["id"]]
    assert slots(client, clinic, TUESDAY)["reason"] == "Clinic holiday: Founders Day"

    # doctor can add own leave
    r = client.post(
        f"/api/v1/doctors/{clinic['doctor_id']}/leaves",
        json={"start_date": "2030-01-09", "end_date": "2030-01-10", "reason": "Conference"},
        headers=clinic["doctor"],
    )
    assert r.status_code == 201
    assert book(client, clinic, day="2030-01-10").status_code == 409
    # receptionist cannot add leave for a doctor
    r = client.post(
        f"/api/v1/doctors/{clinic['doctor_id']}/leaves",
        json={"start_date": "2030-01-11", "end_date": "2030-01-11"},
        headers=clinic["desk"],
    )
    assert r.status_code == 403


def test_slot_cannot_be_double_booked(client, clinic):
    assert book(client, clinic).status_code == 201
    other = client.post("/api/v1/patients", json=patient_payload(full_name="Kiran", phone="1112223333"), headers=clinic["desk"])
    r = book(client, clinic, pid=other.json()["patient_id"])
    assert r.status_code == 409


# --- reschedule / cancel ----------------------------------------------------


def test_cancel_and_reschedule_release_slots(client, clinic):
    appt = book(client, clinic).json()
    r = client.post(f"{API}/{appt['id']}/reschedule", json={"date": MONDAY, "start_time": "09:30"}, headers=clinic["desk"])
    assert r.status_code == 200 and r.json()["start_time"] == "09:30"
    assert r.json()["reschedule_history"][0]["from_time"] == "09:00"
    statuses = {s["start"]: s["status"] for s in slots(client, clinic)["slots"]}
    assert statuses["09:00"] == "available" and statuses["09:30"] == "booked"

    r = client.post(f"{API}/{appt['id']}/cancel", json={"reason": "Feeling better"}, headers=clinic["desk"])
    assert r.json()["status"] == "cancelled"
    assert all(s["status"] == "available" for s in slots(client, clinic)["slots"])


def test_patient_books_online_and_manages_own_appointments(client, clinic, make_user):
    owner = make_user("patient")
    pid = client.post("/api/v1/patients", json=patient_payload(relationship="self", phone="5556667777"), headers=owner).json()[
        "patient_id"
    ]
    r = book(client, clinic, headers=owner, pid=pid)
    assert r.status_code == 201 and r.json()["source"] == "online"
    # cannot book for someone else's record
    assert book(client, clinic, headers=owner, time="09:15").status_code == 404
    assert [a["patient_id"] for a in client.get(API, headers=owner).json()] == [pid]
    r = client.post(f"{API}/{r.json()['id']}/reschedule", json={"date": TUESDAY, "start_time": "09:45"}, headers=owner)
    assert r.status_code == 200
    # patients cannot check in or move the queue
    assert client.post(f"{API}/{r.json()['id']}/check-in", headers=owner).status_code == 403


# --- queue -------------------------------------------------------------------


def test_queue_tokens_and_status_flow(client, clinic):
    first = book(client, clinic, time="09:30").json()
    walk_patient = client.post(
        "/api/v1/patients", json=patient_payload(full_name="Walk In", phone="9990001111"), headers=clinic["desk"]
    ).json()
    walk = client.post(
        f"{API}/walk-in", json={"patient_id": walk_patient["patient_id"], "doctor_id": clinic["doctor_id"]}, headers=clinic["desk"]
    ).json()
    assert walk["token"] == 1 and walk["status"] == "waiting" and walk["start_time"] is None

    checked = client.post(f"{API}/{first['id']}/check-in", headers=clinic["desk"]).json()
    assert checked["token"] == 2 and checked["status"] == "waiting"

    # voicebot step needs consent (fixture patient consented to all three)
    assert client.post(f"{API}/{first['id']}/status", json={"status": "with_voicebot"}, headers=clinic["desk"]).status_code == 200
    # walk-in patient also consented -> but completed is not reachable straight from waiting
    assert client.post(f"{API}/{walk['id']}/status", json={"status": "completed"}, headers=clinic["doctor"]).status_code == 409

    queue = client.get(f"{API}/queue", headers=clinic["doctor"]).json()
    assert [(q["token"], q["status"]) for q in queue] == [(1, "waiting"), (2, "with_voicebot")]


def test_voicebot_requires_consent(client, clinic):
    no_consent = client.post(
        "/api/v1/patients",
        json=patient_payload(full_name="No Consent", phone="8887776666", consent={"data_storage": True}),
        headers=clinic["desk"],
    ).json()
    walk = client.post(
        f"{API}/walk-in", json={"patient_id": no_consent["patient_id"], "doctor_id": clinic["doctor_id"]}, headers=clinic["desk"]
    ).json()
    r = client.post(f"{API}/{walk['id']}/status", json={"status": "with_voicebot"}, headers=clinic["desk"])
    assert r.status_code == 409 and "consented" in r.json()["detail"]


def test_check_in_only_on_the_day(client, clinic):
    appt = book(client, clinic, day=TUESDAY).json()
    assert client.post(f"{API}/{appt['id']}/check-in", headers=clinic["desk"]).status_code == 409


# --- visit types -------------------------------------------------------------


def test_visit_type_new_follow_up_returning(client, clinic, now):
    first = book(client, clinic).json()
    assert first["visit_type"] == "new"
    now(f"{MONDAY}T08:30")
    complete_visit(client, clinic, first["id"], paid=True)

    # within 7 days of the last paid visit -> follow-up
    assert book(client, clinic, day="2030-01-14").json()["visit_type"] == "follow_up"
    # outside the window -> returning
    assert book(client, clinic, day="2030-01-15").json()["visit_type"] == "returning"


def test_unpaid_visit_does_not_start_follow_up_window(client, clinic):
    first = book(client, clinic).json()
    complete_visit(client, clinic, first["id"], paid=False)
    assert book(client, clinic, day=TUESDAY).json()["visit_type"] == "returning"


def test_front_desk_override_requires_reason(client, clinic):
    appt = book(client, clinic).json()
    url = f"{API}/{appt['id']}/visit-type"
    assert client.put(url, json={"visit_type": "follow_up", "reason": " "}, headers=clinic["desk"]).status_code == 422
    assert client.put(url, json={"visit_type": "follow_up"}, headers=clinic["desk"]).status_code == 422
    assert client.put(url, json={"visit_type": "follow_up", "reason": "x"}, headers=clinic["doctor"]).status_code == 403

    r = client.put(url, json={"visit_type": "follow_up", "reason": "Referred back by Dr Shah"}, headers=clinic["desk"])
    body = r.json()
    assert body["visit_type"] == "follow_up" and body["visit_type_auto"] == "new"
    assert body["visit_type_override"]["reason"] == "Referred back by Dr Shah"

    # override survives a reschedule
    r = client.post(f"{API}/{appt['id']}/reschedule", json={"date": TUESDAY, "start_time": "09:00"}, headers=clinic["desk"])
    assert r.json()["visit_type"] == "follow_up"

    assert client.delete(url, headers=clinic["desk"]).json()["visit_type"] == "new"
