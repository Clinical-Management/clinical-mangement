import io

from PIL import Image

from app.prescribing import translate
from tests.test_appointments import API as APPT, book, clinic, now  # noqa: F401
from tests.test_patients import patient_payload

RX = {
    "medicines": [
        {"name": "Dolo 650", "generic": "Paracetamol", "dose": "650 mg", "frequency": "1-1-1", "duration": "3 days", "route": "oral", "instructions": "after food"},
        {"name": "Cetirizine", "dose": "10 mg", "frequency": "0-0-1", "duration": "5 days"},
    ],
    "investigations": [{"name": "CBC"}],
    "advice": "Plenty of fluids.",
    "diet_lifestyle": "Light diet.",
    "referral": {"to": "Dr S. Kulkarni", "specialty": "ENT", "notes": "If no better in 5 days"},
    "follow_up": {"in_days": 5, "note": "Review"},
}


def visit(client, c):
    return book(client, c).json()["id"]


def put_rx(client, c, appt, body=RX):
    return client.put(f"{APPT}/{appt}/prescription", json=body, headers=c["doctor"])


def finalize(client, c, appt, **body):
    return client.post(f"{APPT}/{appt}/prescription/finalize", json=body, headers=c["doctor"])


def test_medicine_search_by_generic_and_brand(client, clinic):
    by_brand = client.get("/api/v1/medicines", params={"q": "dolo"}, headers=clinic["doctor"]).json()
    assert by_brand[0]["generic"] == "Paracetamol" and by_brand[0]["matched_brand"] == "Dolo 650"
    by_generic = client.get("/api/v1/medicines", params={"q": "amox"}, headers=clinic["doctor"]).json()
    assert {m["generic"] for m in by_generic} == {"Amoxicillin", "Amoxicillin + Clavulanic acid"}
    assert by_generic[0]["class_label"] == "Penicillin antibiotic" and by_generic[0]["defaults"]["dose"] == "500 mg"
    assert client.get("/api/v1/medicines", params={"q": "dolo"}, headers=clinic["desk"]).status_code == 403

    # admin adds a clinic-specific brand
    r = client.post("/api/v1/medicines", json={"generic": "Paracetamol + Caffeine", "brands": ["Saridon"], "class": "analgesic"}, headers=clinic["admin"])
    assert r.status_code == 201
    assert client.get("/api/v1/medicines", params={"q": "sarid"}, headers=clinic["doctor"]).json()[0]["generic"] == "Paracetamol + Caffeine"


def test_checks_block_finalize_until_acknowledged(client, clinic):
    client.put(f"/api/v1/patients/{clinic['pid']}/medical", json={"allergies": [{"substance": "Penicillin"}], "current_medications": [{"name": "Warfarin"}]}, headers=clinic["doctor"])
    appt = visit(client, clinic)
    body = {**RX, "medicines": [{"name": "Augmentin 625", "dose": "625 mg", "frequency": "1-0-1"}, {"name": "Brufen", "dose": "400 mg", "frequency": "1-1-1"}]}
    checks = put_rx(client, clinic, appt, body).json()["checks"]
    assert {(c["type"], c["severity"]) for c in checks} == {("allergy", "high"), ("interaction", "high")}

    r = finalize(client, clinic, appt)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "checks_need_acknowledgement" and len(r.json()["detail"]["checks"]) == 2
    assert finalize(client, clinic, appt, acknowledged=True).status_code == 422  # high severity needs a reason
    v = finalize(client, clinic, appt, acknowledged=True, override_reason="Tolerated before; INR monitored").json()
    assert v["version"] == 1 and v["override_reason"].startswith("Tolerated") and len(v["checks"]) == 2


def test_versions_signing_and_verification(client, clinic):
    client.put(f"/api/v1/doctors/{clinic['doctor_id']}/credentials", json={"registration_number": "MMC 2011/04/1234", "registration_council": "Maharashtra Medical Council", "qualifications": "MBBS, MD"}, headers=clinic["doctor"])
    client.put("/api/v1/settings/clinic", json={"name": "Sunrise Family Clinic", "address": "12 MG Road, Pune"}, headers=clinic["admin"])
    assert client.put("/api/v1/settings/clinic", json={"name": "X"}, headers=clinic["doctor"]).status_code == 403

    appt = visit(client, clinic)
    put_rx(client, clinic, appt)
    v1 = finalize(client, clinic, appt).json()
    assert v1["letterhead"]["registration_number"] == "MMC 2011/04/1234" and v1["letterhead"]["clinic_name"] == "Sunrise Family Clinic"
    assert v1["content"]["follow_up"]["date"] == "2030-01-12" and v1["content"]["referral"]["specialty"] == "ENT"
    assert client.get(f"{APPT}/{appt}/prescription", headers=clinic["doctor"]).json()["status"] == "final"

    check = client.get(f"/api/v1/public/prescriptions/{v1['public_id']}").json()  # no login: QR scan
    assert check["valid"] and check["current"] and check["patient_initials"] == "AR"
    assert [m["name"] for m in check["medicines"]] == ["Dolo 650", "Cetirizine"]

    # editing after finalizing starts version 2; v1 stays viewable and reports it was superseded
    edited = put_rx(client, clinic, appt, {**RX, "advice": "Plenty of fluids. Steam inhalation."}).json()
    assert edited["status"] == "draft" and edited["editing_version"] == 2
    v2 = finalize(client, clinic, appt).json()
    versions = client.get(f"{APPT}/{appt}/prescription/versions", headers=clinic["doctor"]).json()
    assert [(v["version"], v["superseded"]) for v in versions] == [(2, False), (1, True)]
    old = client.get(f"/api/v1/public/prescriptions/{v1['public_id']}").json()
    assert old["valid"] and not old["current"] and old["superseded_by_version"] == 2
    assert v2["content"]["advice"].endswith("Steam inhalation.")

    # tampering is detected
    from pymongo import MongoClient
    from app.core.config import settings

    MongoClient(settings.mongodb_uri)[settings.mongodb_db].prescription_versions.update_one(
        {"public_id": v2["public_id"]}, {"$set": {"content.medicines.0.dose": "6500 mg"}}
    )
    assert client.get(f"/api/v1/public/prescriptions/{v2['public_id']}").json()["valid"] is False


def test_pdf_languages_signature_and_translation(client, clinic, monkeypatch):
    calls = []

    async def fake_translate(texts, lang):
        calls.append(lang)
        return [f"[{lang}] {t}" for t in texts]

    monkeypatch.setattr(translate, "translate_free_text", fake_translate)
    sig = io.BytesIO()
    Image.new("RGB", (300, 80), "white").save(sig, "PNG")
    assert client.post(f"/api/v1/doctors/{clinic['doctor_id']}/signature", files={"file": ("sig.png", sig.getvalue())}, headers=clinic["doctor"]).status_code == 204
    assert client.get(f"/api/v1/doctors/{clinic['doctor_id']}", headers=clinic["doctor"]).json()["has_signature"]

    appt = visit(client, clinic)
    put_rx(client, clinic, appt)
    v = finalize(client, clinic, appt).json()
    for lang in ("en", "hi", "mr"):
        r = client.get(f"/api/v1/prescription-versions/{v['id']}/pdf", params={"lang": lang, "copy": "patient"}, headers=clinic["doctor"])
        assert r.status_code == 200 and r.content.startswith(b"%PDF") and r.headers["content-type"] == "application/pdf"
    client.get(f"/api/v1/prescription-versions/{v['id']}/pdf", params={"lang": "hi"}, headers=clinic["doctor"])
    assert calls == ["hi", "mr"]  # translated once per language, then cached


def test_delivery_channels_and_patient_link(client, clinic, make_user):
    appt = visit(client, clinic)
    put_rx(client, clinic, appt)
    v = finalize(client, clinic, appt).json()
    url = f"/api/v1/prescription-versions/{v['id']}/deliver"

    wa = client.post(url, json={"channel": "whatsapp", "language": "hi"}, headers=clinic["desk"]).json()  # front desk sends
    assert wa["status"] == "link_ready" and wa["share_url"].startswith("https://wa.me/919876543210?text=")
    token = wa["link"].split("token=")[1].split("&")[0]
    assert client.get(f"/api/v1/public/prescriptions/{v['public_id']}/patient", params={"token": token}).json()["version"] == 1
    assert client.get(f"/api/v1/public/prescriptions/{v['public_id']}/pdf", params={"token": token, "lang": "hi"}).content.startswith(b"%PDF")
    assert client.get(f"/api/v1/public/prescriptions/{v['public_id']}/patient", params={"token": "wrong-token-123"}).status_code == 404

    sms = client.post(url, json={"channel": "sms", "to": "98111 22233"}, headers=clinic["desk"]).json()
    assert sms["share_url"].startswith("sms:919811122233?body=")
    email = client.post(url, json={"channel": "email"}, headers=clinic["desk"]).json()
    assert email["status"] == "link_ready" and email["share_url"].startswith("mailto:asha@example.com")
    assert client.post(url, json={"channel": "patient_app"}, headers=clinic["desk"]).json()["status"] == "failed"  # walk-in, no account
    assert client.post(url, json={"channel": "print"}, headers=clinic["desk"]).json()["status"] == "recorded"
    log = client.get(f"{APPT}/{appt}/prescription/deliveries", headers=clinic["doctor"]).json()
    assert [d["channel"] for d in log] == ["print", "patient_app", "email", "sms", "whatsapp"]


def test_patient_app_sees_finalized_versions(client, clinic, make_user):
    owner = make_user("patient")
    pid = client.post("/api/v1/patients", json=patient_payload(relationship="self", phone="5556667777"), headers=owner).json()["patient_id"]
    appt = book(client, clinic, pid=pid, headers=owner).json()["id"]
    put_rx(client, clinic, appt)
    v = finalize(client, clinic, appt).json()
    assert client.post(f"/api/v1/prescription-versions/{v['id']}/deliver", json={"channel": "patient_app"}, headers=clinic["doctor"]).json()["status"] == "published"
    mine = client.get(f"{APPT}/{appt}/prescription/versions", headers=owner).json()
    assert [x["version"] for x in mine] == [1]
    assert client.get(f"/api/v1/prescription-versions/{v['id']}/pdf", headers=owner).content.startswith(b"%PDF")
    assert client.get(f"{APPT}/{appt}/prescription", headers=owner).status_code == 403  # drafts stay with the doctor


def test_templates_and_favourites_are_per_doctor(client, clinic, make_user):
    other_doctor = make_user("doctor")
    t = client.post("/api/v1/prescription-templates", json={"name": "Viral fever - adult", "medicines": RX["medicines"], "advice": "Rest"}, headers=clinic["doctor"]).json()
    assert [x["name"] for x in client.get("/api/v1/prescription-templates", headers=clinic["doctor"]).json()] == ["Viral fever - adult"]
    assert client.get("/api/v1/prescription-templates", headers=other_doctor).json() == []
    assert client.delete(f"/api/v1/prescription-templates/{t['id']}", headers=other_doctor).status_code == 404

    fav = {"medicine": {"name": "Dolo 650", "dose": "650 mg", "frequency": "SOS", "duration": "3 days"}}
    client.post("/api/v1/prescription-favourites", json=fav, headers=clinic["doctor"])
    client.post("/api/v1/prescription-favourites", json={"medicine": {**fav["medicine"], "frequency": "1-1-1"}}, headers=clinic["doctor"])
    favs = client.get("/api/v1/prescription-favourites", headers=clinic["doctor"]).json()
    assert len(favs) == 1 and favs[0]["medicine"]["frequency"] == "1-1-1"  # same medicine updates the favourite
