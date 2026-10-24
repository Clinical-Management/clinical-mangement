import time

import jwt
from pymongo import MongoClient

from app.core import totp
from app.core.config import settings

API = "/api/v1"


def _db():
    return MongoClient(settings.mongodb_uri)[settings.mongodb_db]


def _staff(client, admin, email="dr@clinic.com", role="doctor"):
    r = client.post(f"{API}/admin/users", json={"email": email, "full_name": "Dr Test", "password": "password123", "role": role}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def _login(client, email, password="password123"):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def test_staff_mfa_setup_sign_in_and_recovery(client, make_user):
    admin = make_user("admin")
    _staff(client, admin)
    assert client.put(f"{API}/admin/security", json={"staff_mfa_required": True}, headers=admin).status_code == 200

    first = _login(client, "dr@clinic.com").json()
    assert first["mfa_setup_required"] and first["access_token"] is None
    # the MFA token is not a session
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {first['mfa_token']}"}).status_code == 401

    setup = client.post(f"{API}/auth/mfa/setup", json={"mfa_token": first["mfa_token"]}).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/") and setup["qr_png"].startswith("data:image/png")
    assert client.post(f"{API}/auth/mfa/enable", json={"mfa_token": first["mfa_token"], "code": "000000"}).status_code == 422
    enabled = client.post(f"{API}/auth/mfa/enable", json={"mfa_token": first["mfa_token"], "code": totp.now_code(setup["secret"])}).json()
    assert len(enabled["recovery_codes"]) == 8 and enabled["session"]["user"]["mfa_enabled"] is True
    assert "pending_secret" not in _db().users.find_one({"email": "dr@clinic.com"})["mfa"]

    second = _login(client, "dr@clinic.com").json()
    assert second["mfa_required"] and not second["mfa_setup_required"]
    bad = client.post(f"{API}/auth/mfa/verify", json={"mfa_token": second["mfa_token"], "code": "123456"})
    assert bad.status_code == 401
    # the code used to enable can't be replayed; the next one works once
    assert client.post(f"{API}/auth/mfa/verify", json={"mfa_token": second["mfa_token"], "code": totp.now_code(setup["secret"])}).status_code == 401
    nxt = totp.now_code(setup["secret"], time.time() + 30)
    ok = client.post(f"{API}/auth/mfa/verify", json={"mfa_token": second["mfa_token"], "code": nxt})
    assert ok.status_code == 200 and ok.json()["access_token"]
    assert client.post(f"{API}/auth/mfa/verify", json={"mfa_token": second["mfa_token"], "code": nxt}).status_code == 401

    recovery = enabled["recovery_codes"][0]
    assert client.post(f"{API}/auth/mfa/verify", json={"mfa_token": second["mfa_token"], "code": recovery}).status_code == 200
    assert client.post(f"{API}/auth/mfa/verify", json={"mfa_token": second["mfa_token"], "code": recovery}).status_code == 401

    # lost phone: the admin resets, and setup is asked again
    uid = _db().users.find_one({"email": "dr@clinic.com"})["_id"]
    assert client.post(f"{API}/admin/users/{uid}/reset-mfa", headers=admin).status_code == 204
    assert _login(client, "dr@clinic.com").json()["mfa_setup_required"]


def test_patients_never_need_mfa_and_lockout(client, make_user):
    admin = make_user("admin")
    client.put(f"{API}/admin/security", json={"staff_mfa_required": True}, headers=admin)
    client.post(f"{API}/auth/register", json={"email": "p@x.com", "full_name": "Pat", "password": "password123"})
    assert _login(client, "p@x.com").json()["access_token"]

    for _ in range(5):
        assert _login(client, "p@x.com", "wrong-pass").status_code == 401
    # locked for a while, even with the right password
    assert _login(client, "p@x.com").status_code == 401
    _db().users.update_one({"email": "p@x.com"}, {"$unset": {"locked_until": ""}})
    assert _login(client, "p@x.com").status_code == 200


def test_session_refresh_and_absolute_limit(client, make_user):
    headers = make_user("receptionist")
    token = headers["Authorization"][7:]
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert claims["exp"] - claims["iat"] == settings.staff_idle_minutes * 60

    r = client.post(f"{API}/auth/refresh", headers=headers)
    assert r.status_code == 200
    assert jwt.decode(r.json()["access_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm])["auth_time"] == claims["auth_time"]

    stale = jwt.encode({**claims, "auth_time": int(time.time()) - (settings.staff_session_max_hours + 1) * 3600}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    assert client.post(f"{API}/auth/refresh", headers={"Authorization": f"Bearer {stale}"}).status_code == 401


def test_staff_management(client, make_user):
    admin = make_user("admin")
    desk = _staff(client, admin, "desk@clinic.com", "receptionist")
    r = client.patch(f"{API}/admin/users/{desk['id']}", json={"is_active": False}, headers=admin)
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert _login(client, "desk@clinic.com").status_code == 401

    me = _db().users.find_one({"role": "admin"})
    assert client.patch(f"{API}/admin/users/{me['_id']}", json={"role": "doctor"}, headers=admin).status_code == 409  # last admin
    assert client.post(f"{API}/admin/users/{desk['id']}/password", json={"password": "new-password-1"}, headers=admin).status_code == 204
    client.patch(f"{API}/admin/users/{desk['id']}", json={"is_active": True}, headers=admin)
    assert _login(client, "desk@clinic.com", "new-password-1").status_code == 200
    staff = client.get(f"{API}/admin/users?staff=true", headers=admin).json()
    assert {u["role"] for u in staff} <= {"admin", "doctor", "receptionist"}


def _patient(client, headers):
    r = client.post(
        f"{API}/patients",
        json={"full_name": "Asha Rao", "gender": "female", "date_of_birth": "1990-05-12", "phone": "9876500001",
              "consent": {"data_storage": True, "voice_recording": True, "ai_processing": True}},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["patient_id"]


def test_audit_log_records_views_and_detects_tampering(client, make_user):
    admin = make_user("admin")
    desk = make_user("receptionist")
    pid = _patient(client, desk)
    assert client.get(f"{API}/patients/{pid}", headers=desk).status_code == 200
    _login(client, "nobody@x.com", "whatever1")

    log = client.get(f"{API}/admin/audit?patient_id={pid}", headers=admin).json()
    assert "view" in [e["action"] for e in log]
    created = client.get(f"{API}/admin/audit?action=create&resource=patients", headers=admin).json()
    assert created[0]["actor_role"] == "receptionist" and created[0]["status"] == 201
    view = next(e for e in log if e["action"] == "view")
    assert view["actor_role"] == "receptionist" and view["patient_id"] == pid and view["path"] == f"/patients/{pid}"
    failed = client.get(f"{API}/admin/audit?action=login_failed", headers=admin).json()
    assert failed[0]["details"]["email"] == "nobody@x.com"

    # reception can't open clinical notes; the attempt is logged as denied
    appt = _db().appointments.insert_one({"patient_id": pid, "doctor_id": None, "date": "2030-01-07"}).inserted_id
    client.get(f"{API}/appointments/{appt}/notes", headers=desk)
    denied = client.get(f"{API}/admin/audit?action=denied", headers=admin).json()
    assert denied and denied[0]["patient_id"] == pid

    assert client.get(f"{API}/admin/audit/verify", headers=admin).json()["ok"] is True
    csv = client.get(f"{API}/admin/audit/export", headers=admin)
    assert csv.headers["content-type"].startswith("text/csv") and pid in csv.text
    activity = client.get(f"{API}/admin/audit/activity", headers=admin).json()
    assert any(a["role"] == "receptionist" and a["counts"].get("view") for a in activity)
    assert client.get(f"{API}/admin/audit", headers=desk).status_code == 403

    db = _db()
    db.audit_log.update_one({"action": "view"}, {"$set": {"actor_role": "admin"}})
    problems = client.get(f"{API}/admin/audit/verify", headers=admin).json()["problems"]
    assert any("changed" in p["issue"] for p in problems)
    db.audit_log.delete_one({"seq": 2})
    problems = client.get(f"{API}/admin/audit/verify", headers=admin).json()["problems"]
    assert any("missing" in p["issue"] for p in problems)


def test_totp_matches_rfc6238_vector():
    # RFC 6238 test secret "12345678901234567890" (SHA1), T=59s -> 94287082 (8 digits) -> last 6: 287082
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp.now_code(secret, 59) == "287082"
    assert totp.verify(secret, "287 082", at=59) is not None
