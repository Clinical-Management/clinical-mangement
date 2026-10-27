"""Next appointment and reminders: follow-up auto-booking, reminder schedule with confirm / change / cancel
links, nudges and the callback list, medicine reminders, and the notification outbox."""

import re

from pymongo import MongoClient

from app.core.config import settings
from app.services import reminder_service
from tests.test_appointments import API as APPT, book, clinic, now  # noqa: F401

API = "/api/v1"


def _db():
    return MongoClient(settings.mongodb_uri)[settings.mongodb_db]


def tick(client, c):
    """What the background worker does every 30 seconds."""
    r = client.post(f"{API}/notifications/run", headers=c["admin"])
    assert r.status_code == 200, r.text
    return r.json()["sent"]


def notes(client, c, **params):
    return client.get(f"{API}/notifications", params=params, headers=c["desk"]).json()


def finalize(client, c, appt, follow_up):
    body = {"medicines": [{"name": "Paracetamol", "dose": "500 mg", "frequency": "1-0-1", "duration": "5 days"}], "follow_up": follow_up}
    assert client.put(f"{APPT}/{appt}/prescription", json=body, headers=c["doctor"]).status_code == 200
    r = client.post(f"{APPT}/{appt}/prescription/finalize", json={"acknowledged": True}, headers=c["doctor"])
    assert r.status_code == 200, r.text
    return r.json()


def test_reminders_follow_schedule_and_links_work(client, clinic, now):
    appt = book(client, clinic, day="2030-01-10", time="09:00").json()["id"]
    assert tick(client, clinic) == 0  # Monday 08:00: the 3-day reminder isn't due until Monday 09:00

    now("2030-01-07T09:30")
    tick(client, clinic)
    sent = notes(client, clinic, kind="reminder")
    # WhatsApp isn't configured in tests: recorded as such, and SMS is tried instead
    assert sorted((n["channel"], n["status"]) for n in sent) == [("sms", "not_configured"), ("whatsapp", "not_configured")]
    assert sent[0]["ref"]["offset_minutes"] == "4320" and "Dr Mehta" in sent[0]["text"]
    assert tick(client, clinic) == 0 and len(notes(client, clinic, kind="reminder")) == 2  # not repeated

    # the day before, in the patient's language
    assert client.put(f"{API}/patients/{clinic['pid']}/communication", json={"language": "hi", "channels": ["sms"]}, headers=clinic["doctor"]).status_code == 403
    assert client.put(f"{API}/patients/{clinic['pid']}/communication", json={"language": "hi", "channels": ["sms"]}, headers=clinic["desk"]).status_code == 200
    now("2030-01-09T10:00")
    tick(client, clinic)
    latest = notes(client, clinic, kind="reminder")[0]
    assert latest["channel"] == "sms" and latest["language"] == "hi" and "याद" in latest["text"] and "10 जनवरी 2030" in latest["text"]

    # the link in the message works without signing in
    link = re.search(r"/a/(\w+)\?t=([\w-]+)", latest["text"])
    appt_id, token = link.groups()
    assert appt_id == appt
    page = client.get(f"{API}/public/appointments/{appt}", params={"t": token}).json()
    assert page["can_change"] and not page["confirmed"] and page["patient_first_name"]
    assert client.get(f"{API}/public/appointments/{appt}", params={"t": "x" * 20}).status_code == 404
    assert client.post(f"{API}/public/appointments/{appt}/confirm", params={"t": token}).json()["confirmed"] is True

    slots = client.get(f"{API}/public/appointments/{appt}/slots", params={"t": token, "date": "2030-01-11"}).json()
    assert slots["bookable"]
    moved = client.post(f"{API}/public/appointments/{appt}/reschedule", params={"t": token}, json={"date": "2030-01-11", "start_time": "09:30"}).json()
    assert (moved["date"], moved["start_time"]) == ("2030-01-11", "09:30")
    history = client.get(f"{APPT}/{appt}", headers=clinic["desk"]).json()["reschedule_history"]
    assert history[-1]["by_role"] == "patient"
    cancelled = client.post(f"{API}/public/appointments/{appt}/cancel", params={"t": token}, json={"reason": "Feeling better"}).json()
    assert cancelled["status"] == "cancelled" and not cancelled["can_change"]


def test_follow_up_is_booked_moved_and_cancelled_with_the_prescription(client, clinic):
    visit = book(client, clinic).json()["id"]
    finalize(client, clinic, visit, {"in_days": 7, "note": "Review"})
    fu = client.get(f"{APPT}/{visit}/follow-up", headers=clinic["desk"]).json()["appointment"]
    assert (fu["date"], fu["start_time"], fu["source"]) == ("2030-01-14", "09:00", "follow_up")
    booked_msg = notes(client, clinic, kind="follow_up_booked")
    assert booked_msg and "14 Jan 2030" in booked_msg[0]["text"]

    # the doctor changes the advice: the same booking moves
    client.put(f"{APPT}/{visit}/prescription", json={"medicines": [{"name": "Paracetamol"}], "follow_up": {"in_days": 10}}, headers=clinic["doctor"])
    client.post(f"{APPT}/{visit}/prescription/finalize", json={"acknowledged": True}, headers=clinic["doctor"])
    moved = client.get(f"{APPT}/{visit}/follow-up", headers=clinic["desk"]).json()["appointment"]
    assert moved["id"] == fu["id"] and moved["date"] == "2030-01-17"

    # follow-up removed: the booking is cancelled
    client.put(f"{APPT}/{visit}/prescription", json={"medicines": [{"name": "Paracetamol"}], "follow_up": None}, headers=clinic["doctor"])
    client.post(f"{APPT}/{visit}/prescription/finalize", json={"acknowledged": True}, headers=clinic["doctor"])
    assert client.get(f"{APPT}/{fu['id']}", headers=clinic["desk"]).json()["status"] == "cancelled"

    free = client.get(f"{API}/doctors/{clinic['doctor_id']}/next-free", params={"on_or_after": "2030-01-13"}, headers=clinic["desk"]).json()
    assert free[0]["date"] == "2030-01-14"  # Sunday is skipped


def test_unbooked_follow_up_nudge_and_callback_list(client, clinic, now):
    visit = book(client, clinic).json()["id"]
    finalize(client, clinic, visit, {"in_days": 3})
    fu = client.get(f"{APPT}/{visit}/follow-up", headers=clinic["desk"]).json()["appointment"]
    client.post(f"{APPT}/{fu['id']}/cancel", json={"reason": "Patient will call back"}, headers=clinic["desk"])

    rows = client.get(f"{API}/follow-ups/callbacks", headers=clinic["desk"]).json()
    assert [(r["appointment_id"], r["follow_up_date"]) for r in rows] == [(visit, "2030-01-10")]
    assert client.get(f"{API}/follow-ups/callbacks", headers=clinic["doctor"]).status_code == 403

    now("2030-01-11T10:00")  # a day past the advised date
    tick(client, clinic)
    nudges = notes(client, clinic, kind="follow_up_nudge")
    assert nudges and "10 Jan 2030" in nudges[0]["text"]
    tick(client, clinic)
    assert len(notes(client, clinic, kind="follow_up_nudge")) == len(nudges)  # once only
    due = client.get(f"{API}/follow-ups/due", headers=clinic["doctor"]).json()
    assert due["overdue"][0]["overdue_days"] == 1

    client.post(f"{API}/follow-ups/callbacks/{visit}", json={"outcome": "declined", "note": "Going to another city"}, headers=clinic["desk"])
    assert client.get(f"{API}/follow-ups/callbacks", headers=clinic["desk"]).json() == []
    assert client.get(f"{API}/follow-ups/callbacks", params={"include_closed": True}, headers=clinic["desk"]).json()[0]["last_call"]["outcome"] == "declined"

    # booking the visit clears it for good
    book(client, clinic, day="2030-01-12", time="09:00")
    assert client.get(f"{API}/follow-ups/callbacks", params={"include_closed": True}, headers=clinic["desk"]).json() == []


def test_medicine_schedule_parsing():
    assert reminder_service.dose_times("1-0-1") == ["08:00", "20:00"]
    assert reminder_service.dose_times("1-1-1") == ["08:00", "14:00", "20:00"]
    assert reminder_service.dose_times("BD") == ["08:00", "20:00"]
    assert reminder_service.dose_times("once daily") == ["08:00"]
    assert reminder_service.dose_times("SOS") == []
    assert reminder_service.duration_days("5 days") == 5
    assert reminder_service.duration_days("2 weeks") == 14
    assert reminder_service.duration_days("3 months") == 30  # capped
    assert reminder_service.duration_days("till review") == 0


def test_medicine_reminders_and_patient_inbox(client, clinic, make_user):
    patient_headers = make_user("patient")
    me = client.get(f"{API}/auth/me", headers=patient_headers).json()
    from bson import ObjectId

    _db().patients.update_one({"patient_id": clinic["pid"]}, {"$set": {"managed_by": ObjectId(me["id"])}})
    visit = book(client, clinic).json()["id"]
    version = finalize(client, clinic, visit, None)

    r = client.post(f"{API}/prescription-versions/{version['id']}/medicine-reminders", headers=patient_headers)
    assert r.status_code == 200, r.text
    assert r.json()["scheduled"] == 9  # twice a day for 5 days; today's 08:00 dose is already due (it's 08:00)
    scheduled = notes(client, clinic, kind="medicine", status="scheduled")
    assert {n["channel"] for n in scheduled} == {"app", "whatsapp"} and len(scheduled) == 18
    assert client.delete(f"{API}/prescription-versions/{version['id']}/medicine-reminders", headers=patient_headers).status_code == 204
    assert notes(client, clinic, kind="medicine", status="scheduled") == []

    t = client.post(f"{API}/prescription-versions/{version['id']}/test-reminders", json={"date": "2030-02-07", "tests": ["HbA1c"]}, headers=patient_headers)
    assert t.json()["messages"] == 2

    # app messages land in the patient's inbox once sent
    _make_due(clinic["pid"])
    tick(client, clinic)
    inbox = client.get(f"{API}/me/notifications", headers=patient_headers).json()
    assert inbox and inbox[0]["channel"] == "app" and inbox[0]["read_at"] is None
    assert client.post(f"{API}/me/notifications/read", headers=patient_headers).status_code == 204


def _make_due(pid):
    """Make the repeat-test reminder due now."""
    from datetime import datetime, timezone

    _db().notifications.update_many({"patient_id": pid, "kind": "repeat_test"}, {"$set": {"scheduled_at": datetime(2000, 1, 1, tzinfo=timezone.utc)}})
