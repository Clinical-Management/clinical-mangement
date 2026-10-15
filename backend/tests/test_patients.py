from datetime import date, datetime, timezone

from app.services.patient_service import current_age, name_key, phone_key

API = "/api/v1/patients"


def patient_payload(**overrides) -> dict:
    data = {
        "full_name": "Asha Rao",
        "date_of_birth": "1990-05-12",
        "gender": "female",
        "phone": "+91 98765 43210",
        "email": "asha@example.com",
        "address": {"line1": "12 MG Road", "city": "Pune"},
        "emergency_contact": {"name": "Ravi Rao", "relationship": "Husband", "phone": "9876500000"},
        "blood_group": "B+",
        "consent": {"data_storage": True, "voice_recording": True, "ai_processing": True},
    }
    data.update(overrides)
    return data


# --- pure helpers ------------------------------------------------------------


def test_phone_key_ignores_country_code_and_formatting():
    assert phone_key("+91 98765-43210") == phone_key("9876543210") == "9876543210"


def test_name_key_normalises_case_spacing_and_punctuation():
    assert name_key("  Asha   R. Rao ") == name_key("asha r rao")


def test_age_from_dob_and_from_stated_age():
    assert current_age({"date_of_birth": "2000-06-15"}, today=date(2026, 6, 14)) == 25
    assert current_age({"date_of_birth": "2000-06-15"}, today=date(2026, 6, 15)) == 26
    stated = {"stated_age": 40, "stated_age_at": datetime(2024, 1, 1, tzinfo=timezone.utc)}
    assert current_age(stated, today=date(2026, 1, 1)) == 42


# --- API ---------------------------------------------------------------------


def test_admin_registers_patient_with_id_and_consent(client, make_user):
    admin = make_user("admin")
    r = client.post(API, json=patient_payload(), headers=admin)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == "CMP-000001"
    assert body["voicebot_allowed"] is True
    assert body["managed_by"] is None

    second = client.post(API, json=patient_payload(full_name="Someone Else", phone="1112223333"), headers=admin)
    assert second.json()["patient_id"] == "CMP-000002"


def test_data_storage_consent_is_required(client, make_user):
    r = client.post(API, json=patient_payload(consent={"data_storage": False}), headers=make_user("admin"))
    assert r.status_code == 422


def test_dob_or_age_required(client, make_user):
    r = client.post(API, json=patient_payload(date_of_birth=None), headers=make_user("admin"))
    assert r.status_code == 422
    r = client.post(API, json=patient_payload(date_of_birth=None, age=34), headers=make_user("admin"))
    assert r.status_code == 201 and r.json()["age"] == 34


def test_duplicate_detection_by_phone_plus_name_or_dob(client, make_user):
    admin = make_user("admin")
    client.post(API, json=patient_payload(), headers=admin)

    # same phone (different formatting) + same name
    r = client.post(API, json=patient_payload(phone="9876543210", date_of_birth="1991-01-01"), headers=admin)
    assert r.status_code == 409
    assert r.json()["detail"]["matches"][0]["matched_on"] == ["phone", "name"]

    # same phone + same DOB, different name
    r = client.post(API, json=patient_payload(full_name="A. Rao"), headers=admin)
    assert r.status_code == 409

    # same phone, different name and DOB -> family member, not a duplicate
    r = client.post(API, json=patient_payload(full_name="Kiran Rao", date_of_birth="2018-03-03"), headers=admin)
    assert r.status_code == 201

    # override after review is allowed and flagged
    r = client.post(API, json=patient_payload(allow_duplicate=True), headers=admin)
    assert r.status_code == 201 and r.json()["possible_duplicates"] == ["CMP-000001"]
    flagged = client.get(API, params={"flagged": True}, headers=admin).json()
    assert [p["patient_id"] for p in flagged] == [r.json()["patient_id"]]


def test_family_profiles_for_patient_account(client, make_user):
    owner = make_user("patient")
    me = client.post(API, json=patient_payload(relationship="self"), headers=owner)
    assert me.status_code == 201
    child = client.post(
        API, json=patient_payload(full_name="Kiran Rao", date_of_birth="2018-03-03", relationship="child"), headers=owner
    )
    assert child.status_code == 201

    # only one "self" profile; relationship is required
    assert client.post(API, json=patient_payload(full_name="X", relationship="self", phone="1231231234"), headers=owner).status_code == 409
    assert client.post(API, json=patient_payload(full_name="Y", phone="1231231234"), headers=owner).status_code == 422

    mine = client.get(API, headers=owner).json()
    assert [p["relationship"] for p in mine] == ["self", "child"]
    family = client.get(f"{API}/{me.json()['patient_id']}/family", headers=owner).json()
    assert [p["full_name"] for p in family] == ["Kiran Rao"]


def test_patient_cannot_see_other_records(client, make_user):
    walk_in = client.post(API, json=patient_payload(), headers=make_user("admin")).json()
    other = make_user("patient")
    assert client.get(f"{API}/{walk_in['patient_id']}", headers=other).status_code == 404

    # duplicate warning does not leak someone else's record
    r = client.post(API, json=patient_payload(relationship="self"), headers=other)
    assert r.status_code == 409 and r.json()["detail"]["matches"] == []


def test_medical_info_and_consent_history(client, make_user):
    admin, doctor = make_user("admin"), make_user("doctor")
    pid = client.post(
        API, json=patient_payload(consent={"data_storage": True}), headers=admin
    ).json()["patient_id"]

    medical = {
        "allergies": [{"substance": "Penicillin", "reaction": "Rash", "severity": "severe"}],
        "chronic_conditions": [{"name": "Type 2 diabetes", "since_year": 2019}],
        "current_medications": [{"name": "Metformin", "dosage": "500 mg", "frequency": "twice daily"}],
    }
    r = client.put(f"{API}/{pid}/medical", json=medical, headers=doctor)
    assert r.status_code == 200
    assert r.json()["medical"]["allergies"][0]["substance"] == "Penicillin"
    assert r.json()["medical_updated_by_role"] == "doctor"

    assert client.get(f"{API}/{pid}", headers=doctor).json()["voicebot_allowed"] is False
    r = client.put(
        f"{API}/{pid}/consent",
        json={"data_storage": True, "voice_recording": True, "ai_processing": True},
        headers=admin,
    )
    assert r.json()["voicebot_allowed"] is True


def test_search_by_id_name_and_phone(client, make_user):
    admin = make_user("admin")
    pid = client.post(API, json=patient_payload(), headers=admin).json()["patient_id"]
    client.post(API, json=patient_payload(full_name="Other Person", phone="5550001111"), headers=admin)

    for q in (pid.lower(), "asha", "43210"):
        assert [p["patient_id"] for p in client.get(API, params={"q": q}, headers=admin).json()] == [pid]


def test_doctor_cannot_register_or_edit_demographics(client, make_user):
    doctor = make_user("doctor")
    assert client.post(API, json=patient_payload(), headers=doctor).status_code == 403
    pid = client.post(API, json=patient_payload(), headers=make_user("admin")).json()["patient_id"]
    body = {k: v for k, v in patient_payload().items() if k != "consent"}
    assert client.put(f"{API}/{pid}", json=body, headers=doctor).status_code == 403


def test_receptionist_front_desk_permissions(client, make_user):
    reception = make_user("receptionist")

    # registers walk-ins, searches, edits details and records consent
    r = client.post(API, json=patient_payload(consent={"data_storage": True}), headers=reception)
    assert r.status_code == 201
    pid = r.json()["patient_id"]
    assert [p["patient_id"] for p in client.get(API, params={"q": pid}, headers=reception).json()] == [pid]
    body = {k: v for k, v in patient_payload(full_name="Asha R Rao").items() if k != "consent"}
    assert client.put(f"{API}/{pid}", json=body, headers=reception).status_code == 200
    r = client.put(
        f"{API}/{pid}/consent", json={"data_storage": True, "voice_recording": True, "ai_processing": True}, headers=reception
    )
    assert r.json()["voicebot_allowed"] is True


def test_receptionist_cannot_see_or_edit_medical_info(client, make_user):
    reception, doctor = make_user("receptionist"), make_user("doctor")
    pid = client.post(API, json=patient_payload(), headers=make_user("admin")).json()["patient_id"]
    client.put(f"{API}/{pid}/medical", json={"allergies": [{"substance": "Penicillin"}]}, headers=doctor)

    assert client.get(f"{API}/{pid}", headers=reception).json()["medical"] is None
    assert client.get(API, headers=reception).json()[0]["medical"] is None
    assert client.get(f"{API}/{pid}", headers=doctor).json()["medical"]["allergies"][0]["substance"] == "Penicillin"
    r = client.put(f"{API}/{pid}/medical", json={"allergies": []}, headers=reception)
    assert r.status_code == 403


def test_admin_can_create_receptionist_account(client, make_user):
    r = client.post(
        "/api/v1/admin/users",
        json={"email": "desk@clinic.com", "full_name": "Front Desk", "password": "password123", "role": "receptionist"},
        headers=make_user("admin"),
    )
    assert r.status_code == 201 and r.json()["role"] == "receptionist"
    login = client.post("/api/v1/auth/login", json={"email": "desk@clinic.com", "password": "password123"})
    assert login.json()["user"]["role"] == "receptionist"
