"""Billing and fee rules: hand-calculated totals, visit-type fee selection, approvals, split payments,
refunds, receipts and the daily collection report."""

import pytest

from app.billing import calc
from app.services.billing_service import financial_year
from tests.test_appointments import API as APPT, book, clinic, complete_visit, now  # noqa: F401

FEES = {"new": 600, "follow_up": 200, "returning": 400, "emergency": 1000, "teleconsultation": 300}


def set_doctor(client, c, fees=FEES, follow_up_days=7, free_follow_ups=None):
    weekly = [{"weekday": d, "start": "09:00", "end": "10:00"} for d in range(6)]
    r = client.put(
        f"/api/v1/doctors/{c['doctor_id']}/schedule",
        json={"slot_minutes": 15, "follow_up_days": follow_up_days, "free_follow_ups": free_follow_ups, "weekly": weekly, "fees": fees},
        headers=c["admin"],
    )
    assert r.status_code == 200, r.text


def bill_of(client, c, appt, who="desk"):
    return client.get(f"{APPT}/{appt}/bill", headers=c[who]).json()


def pay(client, c, appt, amount, mode="cash", who="desk", reference=None):
    return client.post(f"{APPT}/{appt}/bill/payments", json={"mode": mode, "amount": amount, "reference": reference}, headers=c[who])


# --- arithmetic (hand-calculated) -----------------------------------------------


def test_totals_match_hand_calculation():
    # consultation ₹600 (no GST), dressing ₹150 @18%, 2 injections ₹125 @12%, 10% concession
    lines = [calc.Line(1, 60000, 0), calc.Line(1, 15000, 1800), calc.Line(2, 12500, 1200)]
    discount = calc.discount_for(100000, percent_bp=1000)
    t = calc.compute(lines, discount=discount)
    assert t["subtotal"] == 100000 and t["discount"] == 10000
    # discount spread 6000 / 1500 / 2500 -> taxable 54000 / 13500 / 22500
    assert [l["taxable"] for l in t["lines"]] == [54000, 13500, 22500]
    assert [l["tax"] for l in t["lines"]] == [0, 2430, 2700]  # 18% of 135.00 = 24.30, 12% of 225.00 = 27.00
    assert t["tax_by_rate"] == [
        {"rate_bp": 1200, "taxable": 22500, "tax": 2700, "cgst": 1350, "sgst": 1350},
        {"rate_bp": 1800, "taxable": 13500, "tax": 2430, "cgst": 1215, "sgst": 1215},
    ]
    # 900.00 + 51.30 = 951.30 -> rounded to ₹951, round off -0.30
    assert (t["total"], t["round_off"]) == (95100, -30)
    assert calc.compute(lines, discount=discount, round_to_rupee=False)["total"] == 95130


def test_rounding_and_allocation_are_exact():
    assert calc.allocate(100, [1, 1, 1]) == [34, 33, 33]
    assert sum(calc.allocate(997, [333, 1, 50000, 7])) == 997
    assert calc.compute([calc.Line(1, 10050)])["total"] == 10100  # 100.50 rounds up
    assert calc.compute([calc.Line(1, 10049)])["total"] == 10000
    assert calc.compute([calc.Line(1, 999, 500)])["tax"] == 50  # 5% of 9.99 = 0.4995 -> 0.50
    assert calc.discount_for(500, fixed=900) == 500  # never more than the subtotal
    assert calc.to_paise("123.45") == 12345 and calc.to_paise(80) == 8000 and calc.to_paise("0.5") == 50
    assert calc.rupees(12345) == "123.45" and calc.rupees(-5) == "-0.05"
    with pytest.raises(ValueError):
        calc.rate_bp(7)
    assert financial_year(__import__("datetime").date(2030, 1, 7)) == "2029-30"
    assert financial_year(__import__("datetime").date(2030, 4, 1)) == "2030-31"


# --- fee selection from the visit type (PRD acceptance example) ------------------


def test_follow_up_rate_within_window_standard_rate_outside(client, clinic):
    set_doctor(client, clinic)
    first = book(client, clinic).json()["id"]
    assert bill_of(client, clinic, first)["total"] == 60000  # new visit
    complete_visit(client, clinic, first)
    assert bill_of(client, clinic, first)["status"] == "paid"

    # last paid visit 5 days ago -> follow-up rate; 10 days ago -> standard (returning) rate
    five = book(client, clinic, day="2030-01-12").json()
    ten = book(client, clinic, day="2030-01-17").json()
    assert five["visit_type"] == "follow_up" and bill_of(client, clinic, five["id"])["total"] == 20000
    assert ten["visit_type"] == "returning" and bill_of(client, clinic, ten["id"])["total"] == 40000


def test_free_follow_up_limit_and_paid_follow_up_does_not_restart_window(client, clinic, now):
    set_doctor(client, clinic, fees={**FEES, "follow_up": 0}, free_follow_ups=1)
    first = book(client, clinic).json()["id"]
    complete_visit(client, clinic, first)
    second = book(client, clinic, day="2030-01-08").json()
    assert second["visit_type"] == "follow_up"
    assert bill_of(client, clinic, second["id"])["total"] == 0
    now("2030-01-08T08:00")
    complete_visit(client, clinic, second["id"])  # settled at ₹0, still a receipt
    assert bill_of(client, clinic, second["id"])["status"] == "paid"
    # the one free follow-up is used up
    assert book(client, clinic, day="2030-01-09").json()["visit_type"] == "returning"


def test_fee_override_needs_reason_and_is_audited(client, clinic):
    set_doctor(client, clinic)
    appt = book(client, clinic).json()["id"]
    url = f"{APPT}/{appt}/bill"
    assert client.put(url, json={"fee": {"basis": "emergency"}}, headers=clinic["desk"]).status_code == 422
    bill = client.put(url, json={"fee": {"basis": "emergency", "reason": "Came in at 11 pm"}}, headers=clinic["desk"]).json()
    assert bill["total"] == 100000 and bill["fee"]["key"] == "emergency" and not bill["items"][0]["auto"]
    log = client.get("/api/v1/admin/audit?action=fee_override", headers=clinic["admin"]).json()
    assert log[0]["details"]["reason"] == "Came in at 11 pm" and log[0]["patient_id"] == clinic["pid"]
    custom = client.put(url, json={"fee": {"basis": "custom", "amount": 45000, "reason": "Package rate"}}, headers=clinic["desk"]).json()
    assert custom["total"] == 45000


def test_specialty_fee_used_when_doctor_has_none(client, clinic):
    set_doctor(client, clinic, fees={})
    client.put(f"/api/v1/doctors/{clinic['doctor_id']}/schedule",
               json={"specialization": "Paediatrics", "slot_minutes": 15, "follow_up_days": 7,
                     "weekly": [{"weekday": d, "start": "09:00", "end": "10:00"} for d in range(6)]}, headers=clinic["admin"])
    appt = book(client, clinic).json()["id"]
    assert bill_of(client, clinic, appt)["fee_missing"]
    assert pay(client, clinic, appt, 0).status_code == 422
    settings = client.get("/api/v1/billing/settings", headers=clinic["admin"]).json()
    settings["specialty_fees"] = {"Paediatrics": {"new": 500}}
    assert client.put("/api/v1/billing/settings", json=settings, headers=clinic["admin"]).status_code == 200
    bill = bill_of(client, clinic, appt)
    assert bill["total"] == 50000 and bill["fee"]["source"] == "specialty"


# --- concessions, items, payments ---------------------------------------------------


def test_concessions_follow_approval_rules(client, clinic):
    set_doctor(client, clinic)
    appt = book(client, clinic).json()["id"]
    url = f"{APPT}/{appt}/bill"
    senior = client.put(url, json={"concession": {"type": "senior"}}, headers=clinic["desk"]).json()
    assert senior["concession"]["status"] == "approved" and senior["discount"] == 6000 and senior["total"] == 54000  # 10% preset

    staff = client.put(url, json={"concession": {"type": "staff"}}, headers=clinic["desk"]).json()
    assert staff["concession"]["status"] == "pending" and staff["discount"] == 0  # 50% is above the 10% limit
    assert pay(client, clinic, appt, 30000).status_code == 409
    approvals = client.get("/api/v1/billing/approvals", headers=clinic["desk"]).json()
    assert approvals["concessions"][0]["type"] == "staff"
    assert client.post(f"{url}/concession/approve", headers=clinic["desk"]).status_code == 403
    assert client.post(f"{url}/concession/approve", headers=clinic["admin"]).json()["total"] == 30000

    assert client.put(url, json={"concession": {"type": "waiver"}}, headers=clinic["desk"]).status_code == 422  # reason needed
    client.put(url, json={"concession": {"type": "waiver", "reason": "Camp patient"}}, headers=clinic["desk"])
    waived = client.post(f"{url}/concession/approve", headers=clinic["admin"]).json()
    assert waived["status"] == "waived" and waived["total"] == 0 and waived["balance"] == 0
    assert client.get(f"{APPT}/{appt}", headers=clinic["desk"]).json()["payment_status"] == "waived"


def test_split_partial_payments_receipts_and_daily_collection(client, clinic):
    set_doctor(client, clinic)
    client.post("/api/v1/billing/services", json={"name": "Dressing (small)", "kind": "dressing", "price": 15000, "tax_rate": 18}, headers=clinic["admin"])
    service = client.get("/api/v1/billing/services", headers=clinic["desk"]).json()[0]
    appt = book(client, clinic).json()["id"]
    url = f"{APPT}/{appt}/bill"
    bill = client.put(url, json={"items": [{"kind": "dressing", "service_id": service["id"], "description": service["name"],
                                            "qty": 1, "unit_price": service["price"], "tax_rate": service["tax_rate"]}]}, headers=clinic["desk"]).json()
    # 600 + 150 + 18% of 150 (27.00) = 777.00
    assert bill["total"] == 77700 and bill["tax"] == 2700

    assert pay(client, clinic, appt, 80000).status_code == 422  # more than due
    first = pay(client, clinic, appt, 50000, "cash").json()
    assert first["bill"]["status"] == "partial" and first["bill"]["balance"] == 27700
    assert first["receipt"]["number"] == "RCP/2029-30/000001" and first["receipt"]["balance"] == 27700
    assert client.get(f"{APPT}/{appt}", headers=clinic["desk"]).json()["payment_status"] == "partial"
    dues = client.get("/api/v1/billing/dues", headers=clinic["desk"]).json()
    assert [(d["appointment_id"], d["balance"]) for d in dues] == [(appt, 27700)]  # part-paid counts as outstanding

    # the fee is fixed once paid: a later visit-type change doesn't reprice it
    client.put(f"{APPT}/{appt}/visit-type", json={"visit_type": "follow_up", "reason": "Same complaint"}, headers=clinic["desk"])
    assert bill_of(client, clinic, appt)["total"] == 77700

    second = pay(client, clinic, appt, 27700, "upi", reference="UPI-4471").json()
    assert second["bill"]["status"] == "paid" and second["receipt"]["number"] == "RCP/2029-30/000002"
    assert pay(client, clinic, appt, 100).status_code == 422
    assert client.put(url, json={"items": []}, headers=clinic["desk"]).status_code == 409

    receipts = client.get(f"{APPT}/{appt}/receipts", headers=clinic["desk"]).json()
    assert [r["amount"] for r in receipts] == [50000, 27700]
    for fmt in ("a5", "thermal"):
        pdf = client.get(f"/api/v1/receipts/{receipts[1]['id']}/pdf", params={"fmt": fmt}, headers=clinic["desk"])
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    # refund: requested at the desk, approved by an admin
    r = client.post(f"{url}/refunds", json={"amount": 10000, "mode": "cash", "reason": "Dressing not done"}, headers=clinic["desk"]).json()
    refund = r["refunds"][0]
    assert refund["status"] == "requested" and r["status"] == "paid"
    assert client.post(f"{url}/refunds", json={"amount": 70000, "mode": "cash", "reason": "Too much"}, headers=clinic["desk"]).status_code == 422
    done = client.post(f"{url}/refunds/{refund['id']}/approve", headers=clinic["admin"]).json()
    assert done["refunded"] == 10000 and done["status"] == "partial" and done["refunds"][0]["receipt_number"] == "RFD/2029-30/000001"

    day = client.get("/api/v1/billing/collections", params={"date": "2030-01-07"}, headers=clinic["desk"]).json()
    assert (day["received"], day["refunded"], day["net"], day["receipt_count"]) == (77700, 10000, 67700, 3)
    receipt_sum = sum(r["amount"] * (1 if r["kind"] == "payment" else -1) for r in day["receipts"])
    assert receipt_sum == day["net"]  # totals match the sum of receipts
    assert {m["mode"]: m["net"] for m in day["by_mode"]} == {"cash": 40000, "upi": 27700}

    recon = client.post("/api/v1/billing/reconciliations", json={"date": "2030-01-07", "counted": {"cash": 39900, "upi": 27700}, "note": "Short by Rs 1"},
                        headers=clinic["desk"]).json()
    assert recon["variance"] == -100
    csv = client.get("/api/v1/billing/export", params={"date_from": "2030-01-07", "date_to": "2030-01-07"}, headers=clinic["desk"])
    assert csv.text.count("\n") == 4 and "RFD/2029-30/000001" in csv.text and "-100.00" in csv.text

    # patient-facing bill list; doctors don't see billing history
    bills = client.get(f"/api/v1/patients/{clinic['pid']}/bills", headers=clinic["desk"]).json()
    assert bills[0]["paid"] == 67700 and len(bills[0]["receipts"]) == 3
    assert client.get(f"/api/v1/patients/{clinic['pid']}/bills", headers=clinic["doctor"]).status_code == 403


def test_cancel_needs_refund_first_and_receipt_delivery(client, clinic):
    set_doctor(client, clinic)
    appt = book(client, clinic).json()["id"]
    url = f"{APPT}/{appt}/bill"
    paid = pay(client, clinic, appt, 60000).json()
    assert client.post(f"{url}/cancel", json={"reason": "Duplicate visit"}, headers=clinic["admin"]).status_code == 409

    sent = client.post(f"/api/v1/receipts/{paid['receipt']['id']}/deliver", json={"channel": "whatsapp"}, headers=clinic["desk"]).json()
    assert sent["status"] == "link_ready" and sent["share_url"].startswith("https://wa.me/91")
    link = sent["link"].split("/api/v1", 1)[1]
    assert client.get(f"/api/v1{link}").content.startswith(b"%PDF")  # public link, no login
    assert client.get(f"/api/v1{link.split('?')[0]}?token=wrong-token-123").status_code == 404

    client.post(f"{url}/refunds", json={"amount": 60000, "mode": "cash", "reason": "Duplicate visit"}, headers=clinic["admin"])
    cancelled = client.post(f"{url}/cancel", json={"reason": "Duplicate visit"}, headers=clinic["admin"]).json()
    assert cancelled["status"] == "cancelled" and cancelled["balance"] == 0
    assert pay(client, clinic, appt, 100).status_code == 409


def test_next_appointment_printed_on_receipt(client, clinic):
    set_doctor(client, clinic)
    appt = book(client, clinic).json()["id"]
    client.put(f"{APPT}/{appt}/prescription", json={"medicines": [{"name": "Paracetamol"}], "follow_up": {"in_days": 7}}, headers=clinic["doctor"])
    receipt = pay(client, clinic, appt, 60000).json()["receipt"]
    assert receipt["next_appointment"]["date"] == "2030-01-14" and receipt["next_appointment"]["booked"] is False
