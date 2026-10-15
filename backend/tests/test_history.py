import re

import pytest

from app.api.v1.routes.history import get_engine_factory
from app.history.engine import EngineError, FieldUpdate, RedFlag, ReviewResult, TurnResult
from app.main import app
from tests.test_appointments import API as APPT_API, MONDAY, book, clinic, complete_visit, now  # noqa: F401
from tests.test_patients import patient_payload

API = "/api/v1/history"


class FakeEngine:
    """Scripted stand-in for Claude: keyword-driven so tests are deterministic."""

    def __init__(self):
        self.calls = []

    async def next_turn(self, ctx):
        text = ctx["transcript"][-1]["text"]
        self.calls.append(("turn", ctx))
        lang = "hi" if re.search(r"[ऀ-ॿ]", text) else "en"
        if "breathing" in text and "model" in text:
            return TurnResult(detected_language=lang, reply="-", field_updates=[], red_flags=[RedFlag(code="breathing_difficulty", evidence=text)], interview_complete=False)
        if "advice" in text:
            return TurnResult(detected_language=lang, reply="Please take paracetamol 500 mg.", field_updates=[], red_flags=[], interview_complete=False)
        updates = [FieldUpdate(key="chief_complaint", value="Headache for 3 days")] if "headache" in text else []
        return TurnResult(
            detected_language=lang, reply="How long has it lasted?", field_updates=updates, red_flags=[], interview_complete="done" in text
        )

    async def review(self, ctx, correction):
        self.calls.append(("review", ctx, correction))
        updates = [FieldUpdate(key="duration", value="2 days")] if correction else []
        return ReviewResult(patient_summary="You told us you have a headache." + (" (corrected)" if correction else ""), field_updates=updates)

    async def doctor_summary(self, ctx):
        return "35F, headache x2 days."


class BrokenEngine(FakeEngine):
    async def next_turn(self, ctx):
        raise EngineError("Could not reach the AI assistant")

    async def doctor_summary(self, ctx):
        raise EngineError("down")


@pytest.fixture
def engine():
    fake = FakeEngine()
    app.dependency_overrides[get_engine_factory] = lambda: (lambda: fake)
    yield fake
    app.dependency_overrides.pop(get_engine_factory, None)


@pytest.fixture
def visit(client, clinic, engine):
    """Today's appointment, checked in (waiting)."""
    appt = book(client, clinic).json()
    client.post(f"{APPT_API}/{appt['id']}/check-in", headers=clinic["desk"])
    return {**clinic, "appt_id": appt["id"]}


def start(client, v, mode="voice", channel="clinic_device", headers=None, language="auto"):
    return client.post(
        f"{API}/sessions",
        json={"appointment_id": v["appt_id"], "mode": mode, "channel": channel, "language": language},
        headers=headers or v["desk"],
    )


def kiosk(started):
    return {"X-History-Token": started["link"]["token"]}, started["session"]["id"]


def say(client, sid, headers, text, path="messages"):
    return client.post(f"{API}/sessions/{sid}/{path}", json={"text": text, "input": "text"}, headers=headers)


def test_kiosk_session_full_flow(client, visit, engine):
    r = start(client, visit)
    assert r.status_code == 201, r.text
    started = r.json()
    assert started["link"]["path"].startswith(f"/voice/{started['session']['id']}?token=")
    assert "Hindi" in started["session"]["transcript"][0]["text"]  # trilingual greeting in auto mode
    h, sid = kiosk(started)

    # appointment moved onto the voicebot
    assert client.get(f"{APPT_API}/{visit['appt_id']}", headers=visit["desk"]).json()["status"] == "with_voicebot"

    view = say(client, sid, h, "I have a headache").json()
    assert view["transcript"][-1]["text"] == "How long has it lasted?"

    # Hindi detected -> session language follows (auto mode)
    assert say(client, sid, h, "मुझे सिर दर्द है").json()["language"] == "hi"

    view = say(client, sid, h, "that's all, done").json()
    assert view["status"] == "review" and view["patient_summary"].startswith("You told us")

    view = say(client, sid, h, "Actually it started 2 days ago", path="correct").json()
    assert view["patient_summary"].endswith("(corrected)")

    view = client.post(f"{API}/sessions/{sid}/submit", headers=h).json()
    assert view["status"] == "submitted"

    # doctor sees structured fields + AI summary; queue is back to waiting
    full = client.get(f"{API}/sessions/{sid}", headers=visit["doctor"]).json()
    fields = {f["key"]: f for f in full["fields"]}
    assert fields["chief_complaint"]["value"] == "Headache for 3 days"
    assert fields["duration"]["value"] == "2 days" and fields["duration"]["review_status"] == "pending"
    assert full["summary"] == "35F, headache x2 days." and full["summary_source"] == "ai"
    appt = client.get(f"{APPT_API}/{visit['appt_id']}", headers=visit["desk"]).json()
    assert appt["status"] == "waiting" and appt["history_status"] == "submitted"

    # link stops working after submission
    assert say(client, sid, h, "hello").status_code == 403


def test_rule_red_flag_escalates_without_ai(client, visit, engine):
    h, sid = kiosk(start(client, visit).json())
    view = say(client, sid, h, "मुझे सांस लेने में तकलीफ हो रही है").json()
    assert view["status"] == "escalated"
    # urgent advice comes back in the patient's language (Hindi), not the session default
    assert view["language"] == "hi" and "108" in view["transcript"][-1]["text"]
    assert "इमरजेंसी" in view["transcript"][-1]["text"]
    assert engine.calls == []  # the AI was never consulted

    alerts = client.get("/api/v1/alerts", headers=visit["desk"]).json()
    assert len(alerts) == 1 and "Breathing difficulty" in alerts[0]["message"]
    assert client.get("/api/v1/alerts", headers=visit["doctor"]).json()[0]["id"] == alerts[0]["id"]
    appt = client.get(f"{APPT_API}/{visit['appt_id']}", headers=visit["desk"]).json()
    assert appt["red_flag"] is True and appt["status"] == "waiting"

    assert client.post(f"/api/v1/alerts/{alerts[0]['id']}/acknowledge", headers=visit["desk"]).status_code == 200
    assert client.get("/api/v1/alerts", headers=visit["desk"]).json() == []
    # interview is stopped
    assert say(client, sid, h, "hello").status_code == 409


def test_model_red_flag_escalates(client, visit, engine):
    h, sid = kiosk(start(client, visit).json())
    assert say(client, sid, h, "my breathing feels odd - model").json()["status"] == "escalated"
    full = client.get(f"{API}/sessions/{sid}", headers=visit["doctor"]).json()
    assert full["red_flags"][0]["source"] == "model"


def test_medicine_advice_is_never_shown(client, visit, engine):
    h, sid = kiosk(start(client, visit).json())
    reply = say(client, sid, h, "what advice do you have").json()["transcript"][-1]["text"]
    assert "paracetamol" not in reply and "can't give medical advice" in reply


def test_consent_required_per_mode(client, clinic, engine):
    pid = client.post(
        "/api/v1/patients",
        json=patient_payload(full_name="No Voice", phone="7778889999", consent={"data_storage": True, "ai_processing": True}),
        headers=clinic["desk"],
    ).json()["patient_id"]
    appt = book(client, clinic, pid=pid, time="09:15").json()
    v = {**clinic, "appt_id": appt["id"]}
    assert start(client, v, mode="voice").status_code == 409
    assert start(client, v, mode="text").status_code == 201


def test_ai_outage_returns_503_and_staff_can_enter_manually(client, visit):
    app.dependency_overrides[get_engine_factory] = lambda: (lambda: BrokenEngine())
    try:
        h, sid = kiosk(start(client, visit).json())
        r = say(client, sid, h, "I have a headache")
        assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_unavailable"

        # receptionist cannot type medical history; doctor can take over
        assert client.put(f"{API}/sessions/{sid}/manual", json={"fields": {}}, headers=visit["desk"]).status_code == 404
        r = client.put(
            f"{API}/sessions/{sid}/manual",
            json={"fields": {"chief_complaint": "Headache", "allergies": "None known"}},
            headers=visit["doctor"],
        )
        assert r.status_code == 200 and r.json()["mode"] == "manual"
        r = client.post(f"{API}/sessions/{sid}/manual/submit", headers=visit["doctor"])
        body = r.json()
        assert body["status"] == "submitted" and body["summary_source"] == "auto"
        assert "Chief complaint: Headache" in body["summary"]
    finally:
        app.dependency_overrides.pop(get_engine_factory, None)


def test_doctor_review_is_logged(client, visit, engine):
    h, sid = kiosk(start(client, visit).json())
    say(client, sid, h, "I have a headache, done")
    client.post(f"{API}/sessions/{sid}/submit", headers=h)

    url = f"{API}/sessions/{sid}/fields"
    assert client.put(f"{url}/chief_complaint", json={"action": "accept"}, headers=visit["doctor"]).status_code == 200
    r = client.put(f"{url}/chief_complaint", json={"action": "edit", "value": "Frontal headache x3d"}, headers=visit["doctor"])
    body = r.json()
    field = next(f for f in body["fields"] if f["key"] == "chief_complaint")
    assert field["value"] == "Frontal headache x3d" and field["review_status"] == "edited" and field["origin"] == "doctor"
    assert [(e["action"], e["old"], e["new"]) for e in body["edit_log"]] == [
        ("accept", "Headache for 3 days", "Headache for 3 days"),
        ("edit", "Headache for 3 days", "Frontal headache x3d"),
    ]
    r = client.put(f"{API}/sessions/{sid}/summary", json={"summary": "Edited summary"}, headers=visit["doctor"])
    assert r.json()["summary"] == "Edited summary" and r.json()["edit_log"][-1]["field"] == "summary"

    # receptionist and other patients cannot open the clinical view
    assert client.get(f"{API}/sessions/{sid}", headers=visit["desk"]).status_code == 404


def test_returning_patient_gets_stored_data(client, visit, engine, now):
    h, sid = kiosk(start(client, visit).json())
    say(client, sid, h, "I have a headache, done")
    client.post(f"{API}/sessions/{sid}/submit", headers=h)
    # doctor records allergies on the first history, then the visit completes
    first = client.get(f"{API}/sessions/{sid}", headers=visit["doctor"]).json()
    assert first["status"] == "submitted"
    client.put(f"{API}/sessions/{sid}/fields/allergies", json={"action": "edit", "value": "Penicillin (rash)"}, headers=visit["doctor"])
    for s in ("in_consultation", "completed"):
        client.post(f"{APPT_API}/{visit['appt_id']}/status", json={"status": s}, headers=visit["doctor"])

    second = book(client, visit, day="2030-01-08").json()
    now("2030-01-08T08:00")
    client.post(f"{APPT_API}/{second['id']}/check-in", headers=visit["desk"])
    started = start(client, {**visit, "appt_id": second["id"]}).json()
    assert "Welcome back" in started["session"]["transcript"][0]["text"]
    full = client.get(f"{API}/sessions/{started['session']['id']}", headers=visit["doctor"]).json()
    fields = {f["key"]: f for f in full["fields"]}
    assert full["returning"] is True
    assert fields["allergies"]["value"] == "Penicillin (rash)" and fields["allergies"]["origin"] == "previous"
    assert "changes_since_last_visit" in fields


def test_patient_starts_on_own_phone_with_login(client, clinic, engine, make_user):
    owner = make_user("patient")
    pid = client.post("/api/v1/patients", json=patient_payload(relationship="self", phone="5556667777"), headers=owner).json()["patient_id"]
    appt = book(client, clinic, pid=pid, headers=owner, time="09:30").json()
    r = start(client, {**clinic, "appt_id": appt["id"]}, mode="text", channel="patient_device", headers=owner, language="mr")
    assert r.status_code == 201
    sid = r.json()["session"]["id"]
    assert r.json()["session"]["language"] == "mr" and r.json()["session"]["language_mode"] == "manual"
    # works with the login (no token needed)
    assert client.get(f"{API}/sessions/{sid}/patient-view", headers=owner).status_code == 200
    assert say(client, sid, owner, "I have a headache").status_code == 200
    # but not the clinical view (404: existence is not revealed)
    assert client.get(f"{API}/sessions/{sid}", headers=owner).status_code == 404
