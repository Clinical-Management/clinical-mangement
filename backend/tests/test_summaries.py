import pytest

from app.ai.client import EngineError

from app.api.v1.routes.summaries import get_summary_engine_factory
from app.main import app
from app.reports.summarizer import ExtractedTest, ExtractionResult
from tests.test_appointments import book, clinic, now  # noqa: F401
from tests.test_patients import patient_payload
from tests.test_reports import dicom_bytes, pdf_bytes, upload


def lab(name, value, unit, ref, page=1, conf="high"):
    return ExtractedTest(
        name=name, value=value, unit=unit, reference_range=ref, ref_low=None, ref_high=None,
        printed_flag=None, page=page, bbox=[60, 100, 940, 130], source_text=f"{name} {value} {unit} {ref}", confidence=conf,
    )


class FakeEngine:
    """Returns canned extractions in order; records the pages it was shown."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def extract(self, pages, context):
        self.calls.append((len(pages), context))
        return self.results.pop(0)


def lab_result(*tests, summary="Potassium critically high."):
    return ExtractionResult(
        document_kind="lab_report", readability="good", lab_name="City Diagnostics", report_date=None,
        tests=list(tests), findings=None, impression=None, image_observation=None, summary=summary, overall_confidence="high",
    )


@pytest.fixture
def engine():
    def install(*results):
        fake = FakeEngine(results)
        app.dependency_overrides[get_summary_engine_factory] = lambda: (lambda: fake)
        return fake

    yield install
    app.dependency_overrides.pop(get_summary_engine_factory, None)


def summary_of(client, c, report_id, headers=None):
    return client.get(f"/api/v1/reports/{report_id}/summary", headers=headers or c["doctor"])


def test_lab_summary_flags_criticals_and_alerts(client, clinic, engine):
    fake = engine(lab_result(
        lab("Serum Potassium (K+)", "6.8", "mmol/L", "3.5 - 5.1"),
        lab("HbA1c", "7.8", "%", "< 5.7"),
        lab("Haemoglobin", "14.2", "g/dL", "13.0 - 17.0", conf="medium"),
    ))
    appt = book(client, clinic).json()["id"]
    report = upload(client, clinic, pdf_bytes(2), appointment_id=appt).json()

    assert fake.calls[0][0] == 2  # both pages were read
    s = summary_of(client, clinic, report["id"]).json()
    assert s["status"] == "ready" and s["ai_generated"] and "AI-generated" in s["label"]
    rows = {r["analyte_key"]: r for r in s["tests"]}
    assert rows["potassium"]["flag"] == "critical_high" and rows["potassium"]["critical"]
    assert rows["hba1c"]["flag"] == "high" and rows["haemoglobin"]["flag"] == "normal"
    assert rows["haemoglobin"]["confidence"] == "medium"
    assert rows["potassium"]["page"] == 1 and rows["potassium"]["bbox"] == [60, 100, 940, 130]

    alerts = client.get("/api/v1/alerts", headers=clinic["doctor"]).json()
    assert len(alerts) == 1 and "Potassium (K+) 6.8 mmol/L" in alerts[0]["message"]


def test_doctor_edits_and_approval_gate_patient_view(client, clinic, engine, make_user):
    owner = make_user("patient")
    pid = client.post("/api/v1/patients", json=patient_payload(relationship="self", phone="5556667777"), headers=owner).json()["patient_id"]
    engine(lab_result(lab("HbA1c", "7.8", "%", "< 5.7"), lab("Sodium", "38", "mmol/L", "135 - 145")))
    report = upload(client, clinic, pdf_bytes(), headers=owner, pid=pid).json()
    s = summary_of(client, clinic, report["id"]).json()

    # patient sees nothing until approved
    assert summary_of(client, clinic, report["id"], headers=owner).status_code == 404
    assert client.get(f"/api/v1/patients/{pid}/report-summaries", headers=owner).json() == []

    # AI misread sodium 138 as 38 (would be critical): doctor corrects it, flag recomputed, change logged
    sodium = next(r for r in s["tests"] if r["analyte_key"] == "sodium")
    assert sodium["critical"]
    url = f"/api/v1/report-summaries/{s['id']}"
    s = client.patch(f"{url}/tests/{sodium['id']}", json={"value": "138"}, headers=clinic["doctor"]).json()
    sodium = next(r for r in s["tests"] if r["analyte_key"] == "sodium")
    assert sodium["flag"] == "normal" and sodium["edited"] and not sodium["critical"]
    assert s["edit_log"][-1]["changes"] == {"value": ["38", "138"]}

    s = client.post(f"{url}/tests", json={"name": "TSH", "value": "2.1", "unit": "mIU/L", "reference_range": "0.4 - 4.0"}, headers=clinic["doctor"]).json()
    assert s["tests"][-1]["added_by_doctor"] and s["tests"][-1]["confidence"] is None
    s = client.patch(f"{url}/text", json={"summary_text": "HbA1c 7.8% (high). Others normal."}, headers=clinic["doctor"]).json()

    assert client.post(f"{url}/approve", headers=clinic["desk"]).status_code == 403
    s = client.post(f"{url}/approve", headers=clinic["doctor"]).json()
    assert s["status"] == "approved"

    mine = summary_of(client, clinic, report["id"], headers=owner).json()
    assert mine["summary_text"] == "HbA1c 7.8% (high). Others normal." and "approved by your doctor" in mine["label"]
    assert [t["name"] for t in mine["tests"]] == ["HbA1c", "Sodium", "TSH"]

    # editing after approval withdraws it from the patient until re-approved
    client.patch(f"{url}/text", json={"summary_text": "Changed"}, headers=clinic["doctor"])
    assert summary_of(client, clinic, report["id"], headers=owner).status_code == 404


def test_trends_use_earlier_approved_results(client, clinic, engine):
    engine(
        lab_result(lab("HbA1c", "8.4", "%", "< 5.7")),
        lab_result(lab("Glycated Haemoglobin", "7.8", "%", "< 5.7")),
    )
    first = upload(client, clinic, pdf_bytes(), report_date="2029-06-01").json()
    s1 = summary_of(client, clinic, first["id"]).json()
    client.post(f"/api/v1/report-summaries/{s1['id']}/approve", headers=clinic["doctor"])
    second = upload(client, clinic, pdf_bytes(2), report_date="2030-01-02").json()
    s2 = summary_of(client, clinic, second["id"]).json()

    trend = client.get(f"/api/v1/report-summaries/{s2['id']}/trends", headers=clinic["doctor"]).json()
    assert [(p["date"], p["value"], p["current"]) for p in trend["hba1c"]] == [("2029-06-01", 8.4, False), ("2030-01-02", 7.8, True)]


def test_image_only_is_labelled_assistive(client, clinic, engine):
    engine(ExtractionResult(
        document_kind="image_only", readability="partial", lab_name=None, report_date=None, tests=[],
        findings=None, impression=None, image_observation="Possible opacity in the right lower zone.",
        summary="Possible right lower zone opacity.", overall_confidence="low",
    ))
    report = upload(client, clinic, dicom_bytes(), name="chest.dcm", report_type="xray").json()
    s = summary_of(client, clinic, report["id"]).json()
    assert s["label"] == "Assistive, not diagnostic. Requires doctor review."
    assert s["image_observation"].startswith("Possible")


def test_no_consent_and_failures(client, clinic, engine, make_user):
    pid = client.post(
        "/api/v1/patients",
        json=patient_payload(full_name="No AI", phone="7778889999", consent={"data_storage": True}),
        headers=clinic["desk"],
    ).json()["patient_id"]
    fake = engine()
    report = upload(client, clinic, pdf_bytes(), pid=pid).json()
    assert summary_of(client, clinic, report["id"]).json()["status"] == "no_consent" and fake.calls == []

    # AI outage -> failed with a message; the doctor can re-run it later
    class Down:
        async def extract(self, pages, context):
            raise EngineError("Could not reach the AI assistant")

    app.dependency_overrides[get_summary_engine_factory] = lambda: (lambda: Down())
    other = upload(client, clinic, pdf_bytes(3)).json()
    s = summary_of(client, clinic, other["id"]).json()
    assert s["status"] == "failed" and s["error"] == "Could not reach the AI assistant"

    engine(lab_result(lab("HbA1c", "7.8", "%", "< 5.7")))
    rerun = client.post(f"/api/v1/reports/{other['id']}/summary", headers=clinic["doctor"])
    assert rerun.status_code == 202
    assert summary_of(client, clinic, other["id"]).json()["status"] == "ready"


def test_pages_and_access(client, clinic, engine):
    engine(lab_result(lab("HbA1c", "7.8", "%", "< 5.7")))
    report = upload(client, clinic, pdf_bytes(2)).json()
    assert client.get(f"/api/v1/reports/{report['id']}/pages", headers=clinic["doctor"]).json() == {"count": 2}
    page = client.get(f"/api/v1/reports/{report['id']}/pages/2", headers=clinic["doctor"])
    assert page.headers["content-type"] == "image/png" and page.content.startswith(b"\x89PNG")
    assert client.get(f"/api/v1/reports/{report['id']}/pages/3", headers=clinic["doctor"]).status_code == 404
    # receptionists never see clinical summaries or page images
    assert summary_of(client, clinic, report["id"], headers=clinic["desk"]).status_code == 403
    assert client.get(f"/api/v1/reports/{report['id']}/pages/1", headers=clinic["desk"]).status_code == 403
