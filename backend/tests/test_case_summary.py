from app.api.v1.routes.case_summary import get_writer_factory
from app.api.v1.routes.summaries import get_summary_engine_factory
from app.main import app
from tests.test_appointments import API as APPT, book, clinic, now  # noqa: F401
from tests.test_patients import patient_payload
from tests.test_reports import pdf_bytes, upload
from tests.test_summaries import FakeEngine, lab, lab_result


def prepare_visit(client, c):
    appt = book(client, c).json()["id"]
    client.post(f"{APPT}/{appt}/vitals", json={"bp_systolic": 150, "bp_diastolic": 95, "pulse": 80}, headers=c["doctor"])
    client.patch(f"{APPT}/{appt}/notes", json={"examination": "Chest clear."}, headers=c["doctor"])
    client.post(f"{APPT}/{appt}/notes/diagnoses", json={"code": "I10", "status": "provisional"}, headers=c["doctor"])
    client.put(f"{APPT}/{appt}/prescription", json={"medicines": [{"name": "Amlodipine", "dose": "5 mg", "frequency": "1-0-0", "duration": "30 days"}], "advice": "Low salt diet"}, headers=c["doctor"])
    return appt


def sections(summary):
    return {s["key"]: s for s in summary["sections"]}


def test_rules_draft_from_visit_data(client, clinic):
    appt = prepare_visit(client, clinic)
    url = f"{APPT}/{appt}/case-summary"
    assert client.get(url, headers=clinic["doctor"]).status_code == 404

    s = client.post(f"{url}/generate", headers=clinic["doctor"]).json()
    assert s["status"] == "draft" and s["generated_by"] == "rules" and s["generation_note"].startswith("AI unavailable")
    sec = sections(s)
    assert "BP 150/95 mmHg (high)" in sec["key_findings"]["text"] and "Chest clear." in sec["key_findings"]["text"]
    assert sec["diagnosis"]["text"] == "Essential (primary) hypertension (I10, provisional)"
    assert "Amlodipine 5 mg 1-0-0 x 30 days" in sec["plan"]["text"] and "Low salt diet" in sec["plan"]["text"]
    assert not s["stale"]
    assert client.get(url, headers=clinic["desk"]).status_code == 403


def test_ai_draft_only_with_consent(client, clinic, make_user):
    class Writer:
        async def write(self, ctx):
            self.ctx = ctx
            return {k: f"AI {k}" for k in ("chief_complaint", "history", "key_findings", "report_results", "diagnosis", "plan")}

    writer = Writer()
    app.dependency_overrides[get_writer_factory] = lambda: (lambda: writer)
    appt = prepare_visit(client, clinic)
    s = client.post(f"{APPT}/{appt}/case-summary/generate", headers=clinic["doctor"]).json()
    assert s["generated_by"] == "ai" and sections(s)["plan"]["text"] == "AI plan"
    assert writer.ctx["diagnoses"][0]["code"] == "I10"

    no_ai = client.post(
        "/api/v1/patients", json=patient_payload(full_name="No AI", phone="7778889999", consent={"data_storage": True}), headers=clinic["desk"]
    ).json()["patient_id"]
    other = book(client, clinic, pid=no_ai, time="09:15").json()["id"]
    s = client.post(f"{APPT}/{other}/case-summary/generate", headers=clinic["doctor"]).json()
    assert s["generated_by"] == "rules" and "not consented" in s["generation_note"]


def test_regenerate_shows_changes_and_keeps_doctor_edits(client, clinic):
    appt = prepare_visit(client, clinic)
    url = f"{APPT}/{appt}/case-summary"
    client.post(f"{url}/generate", headers=clinic["doctor"])

    # doctor rewrites the diagnosis section freely
    s = client.put(url, json={"sections": {"diagnosis": "Stage 2 hypertension, newly detected."}}, headers=clinic["doctor"]).json()
    assert sections(s)["diagnosis"]["edited"]

    # new information: an approved lab report, more examination notes, diagnosis made final
    fake = FakeEngine([lab_result(lab("Serum Potassium", "3.1", "mmol/L", "3.5 - 5.1"))])
    app.dependency_overrides[get_summary_engine_factory] = lambda: (lambda: fake)
    report = upload(client, clinic, pdf_bytes(), appointment_id=appt).json()
    summary = client.get(f"/api/v1/reports/{report['id']}/summary", headers=clinic["doctor"]).json()
    client.post(f"/api/v1/report-summaries/{summary['id']}/approve", headers=clinic["doctor"])
    client.patch(f"{APPT}/{appt}/notes", json={"examination": "Chest clear. Mild pedal oedema."}, headers=clinic["doctor"])
    diag = client.get(f"{APPT}/{appt}/notes", headers=clinic["doctor"]).json()["diagnoses"][0]
    client.patch(f"{APPT}/{appt}/notes/diagnoses/{diag['id']}", json={"status": "final"}, headers=clinic["doctor"])

    s = client.get(url, headers=clinic["doctor"]).json()
    assert s["stale"]
    assert set(s["pending_changes"]) == {"New approved report: blood test (2030-01-05)", "Examination notes changed", "Diagnosis changed"}

    s = client.post(f"{url}/generate", headers=clinic["doctor"]).json()
    sec = sections(s)
    assert not s["stale"] and s["version"] == 2
    assert "Potassium 3.1 mmol/L (low)" in sec["report_results"]["text"]
    inserted = "".join(op["text"] for op in sec["key_findings"]["last_change"] if op["op"] == "insert")
    assert "oedema" in inserted
    # edited section kept; the regenerated wording is only a suggestion
    assert sec["diagnosis"]["text"] == "Stage 2 hypertension, newly detected."
    assert sec["diagnosis"]["suggestion"]["text"] == "Essential (primary) hypertension (I10, final)"

    assert client.post(f"{url}/finalize", headers=clinic["doctor"]).status_code == 409  # suggestion pending
    s = client.post(f"{url}/suggestions/diagnosis/dismiss", headers=clinic["doctor"]).json()
    assert sections(s)["diagnosis"]["suggestion"] is None
    assert client.post(f"{url}/finalize", headers=clinic["doctor"]).json()["status"] == "final"
    assert client.put(url, json={"sections": {"plan": "x"}}, headers=clinic["doctor"]).status_code == 409


def test_finalized_summary_in_prescription_with_toggles(client, clinic):
    appt = prepare_visit(client, clinic)
    url = f"{APPT}/{appt}/case-summary"
    printout = client.get(f"{APPT}/{appt}/prescription/print", headers=clinic["doctor"]).json()
    assert printout["case_summary"] == [] and printout["case_summary_status"] is None

    client.post(f"{url}/generate", headers=clinic["doctor"])
    assert client.get(f"{APPT}/{appt}/prescription/print", headers=clinic["doctor"]).json()["case_summary"] == []  # draft: not printed
    client.post(f"{url}/finalize", headers=clinic["doctor"])

    rx = client.get(f"{APPT}/{appt}/prescription", headers=clinic["doctor"]).json()
    client.put(f"{APPT}/{appt}/prescription", json={**{k: rx[k] for k in ("medicines", "investigations", "advice", "follow_up")},
               "summary_sections": {"history": False, "report_results": False}}, headers=clinic["doctor"])
    printout = client.get(f"{APPT}/{appt}/prescription/print", headers=clinic["doctor"]).json()
    # plan is off by default: the prescription lists it already
    assert [s["key"] for s in printout["case_summary"]] == ["chief_complaint", "key_findings", "diagnosis"]
    client.put(f"{APPT}/{appt}/prescription", json={**{k: rx[k] for k in ("medicines", "investigations", "advice", "follow_up")},
               "summary_sections": {"history": False, "report_results": False, "plan": True}}, headers=clinic["doctor"])
    printout = client.get(f"{APPT}/{appt}/prescription/print", headers=clinic["doctor"]).json()
    assert [s["key"] for s in printout["case_summary"]][-1] == "plan"
    assert printout["prescription"]["medicines"][0]["name"] == "Amlodipine"
    assert printout["doctor_name"] == "Dr Mehta" and printout["patient_id"] == clinic["pid"]
