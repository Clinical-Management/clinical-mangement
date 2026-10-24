"""Receipt PDFs: A5 for normal printers and an 80 mm roll for thermal receipt printers."""

from datetime import date, datetime

from fpdf import FPDF

from app.billing.calc import rupees
from app.core.clock import clinic_tz
from app.prescribing.pdf import FONTS, GREY, NAVY

VISIT_LABELS = {"new": "New visit", "follow_up": "Follow-up", "returning": "Returning", "emergency": "Emergency / after-hours",
                "teleconsultation": "Teleconsultation"}
MODES = {"cash": "Cash", "upi": "UPI", "card": "Card", "other": "Other"}
CONCESSIONS = {"senior": "Senior citizen concession", "staff": "Staff concession", "waiver": "Fee waived", "other": "Discount"}


def _money(paise: int) -> str:
    return "Rs " + rupees(paise)


def _when(value: datetime) -> str:
    return value.astimezone(clinic_tz()).strftime("%d %b %Y %I:%M %p")


def _day(value: str) -> str:
    try:
        return date.fromisoformat(value[:10]).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return value or ""


def _age(dob: str | None) -> str:
    if not dob:
        return ""
    born = date.fromisoformat(str(dob)[:10])
    today = date.today()
    return f"{today.year - born.year - ((today.month, today.day) < (born.month, born.day))} y"


def _lines(receipt: dict) -> list[tuple[str, str, str]]:
    """(label, value, style) rows shared by both layouts; style: '' | 'B' | 'small' | 'rule' | 'title'."""
    s = receipt["snapshot"]
    bill, clinic, patient = s["bill"], s["clinic"], s["patient"]
    refund = receipt["kind"] == "refund"
    rows: list[tuple[str, str, str]] = [("REFUND RECEIPT" if refund else "RECEIPT", receipt["number"], "title"),
                                        ("Date", _when(receipt["issued_at"]), "small")]
    rows += [("Patient", f"{patient['name']} ({patient['patient_id']})", ""),
             ("", " | ".join(filter(None, [_age(patient.get("date_of_birth")), (patient.get("gender") or "").title(), patient.get("phone")])), "small"),
             ("Doctor", s["doctor"]["name"], ""),
             ("Visit", f"{_day(s['visit']['date'])} | {VISIT_LABELS.get(s['visit']['visit_type'], s['visit']['visit_type'])}", "small"),
             ("", "", "rule")]
    for item in bill["items"]:
        label = item["description"] + (f" x{item['qty']}" if item["qty"] > 1 else "")
        rows.append((label, _money(item["amount"]), ""))
        if item.get("tax_rate"):
            rows.append((f"  GST {item['tax_rate']:g}%", "", "small"))
    rows.append(("", "", "rule"))
    rows.append(("Subtotal", _money(bill["subtotal"]), ""))
    if bill["discount"]:
        c = s["concession"]
        label = CONCESSIONS.get(c["type"], "Discount") + (f" ({c['percent']:g}%)" if c.get("percent") and c["type"] != "waiver" else "")
        rows.append((label, "- " + _money(bill["discount"]), ""))
    for slab in bill["tax_by_rate"]:
        half = slab["rate_bp"] / 200
        rows.append((f"CGST {half:g}% on {_money(slab['taxable'])}", _money(slab["cgst"]), "small"))
        rows.append((f"SGST {half:g}%", _money(slab["sgst"]), "small"))
    if bill["round_off"]:
        rows.append(("Round off", ("+ " if bill["round_off"] > 0 else "- ") + _money(abs(bill["round_off"])), "small"))
    rows.append(("Total", _money(bill["total"]), "B"))
    rows.append(("", "", "rule"))
    for p in s["payments"]:
        rows.append((f"Paid - {MODES.get(p['mode'], p['mode'])}" + (f" ({p['reference']})" if p.get("reference") else ""), _money(p["amount"]), "small"))
    if refund:
        rows.append((f"Refunded - {MODES.get(receipt['mode'], receipt['mode'])}", "- " + _money(receipt["amount"]), "B"))
        if receipt.get("reason"):
            rows.append(("Reason", receipt["reason"], "small"))
    else:
        rows.append((f"This payment - {MODES.get(receipt['mode'], receipt['mode'])}", _money(receipt["amount"]), "B"))
    rows.append(("Balance due", _money(receipt["balance"]), "B"))
    nxt = receipt.get("next_appointment")
    if nxt:
        rows.append(("", "", "rule"))
        when = _day(nxt["date"]) + (f" at {nxt['time']}" if nxt.get("time") else "")
        rows.append(("Next appointment" if nxt.get("booked") else "Follow-up advised", when, "B"))
    if clinic.get("gstin") and bill["tax"]:
        rows.append(("GSTIN", clinic["gstin"], "small"))
    return rows


def _header(pdf: FPDF, clinic: dict, width: float, center: bool) -> None:
    align = "C" if center else "L"
    pdf.set_text_color(*NAVY)
    pdf.set_font("Noto", "B", 12 if center else 14)
    pdf.multi_cell(width, 6, clinic["name"], align=align, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Noto", "", 7.5)
    pdf.set_text_color(*GREY)
    for line in filter(None, [clinic.get("address"), " | ".join(filter(None, [clinic.get("phone"), clinic.get("email")]))]):
        pdf.multi_cell(width, 3.8, line, align=align, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


def render(receipt: dict, fmt: str = "a5") -> bytes:
    rows = _lines(receipt)
    clinic = receipt["snapshot"]["clinic"]
    thermal = fmt == "thermal"
    if thermal:
        height = 60 + 5 * len(rows) + 4 * sum(1 for label, *_ in rows if len(label) > 26)
        pdf = FPDF(unit="mm", format=(80, height))
        pdf.set_margins(4, 4, 4)
    else:
        pdf = FPDF(unit="mm", format=(148, 210))  # A5
        pdf.set_margins(12, 10, 12)
    pdf.add_font("Noto", "", str(FONTS / "NotoSans-Regular.ttf"))
    pdf.add_font("Noto", "B", str(FONTS / "NotoSans-Bold.ttf"))
    pdf.set_auto_page_break(not thermal, margin=12)
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin
    value_w = 26 if thermal else 40
    _header(pdf, clinic, width, center=thermal)

    for label, value, style in rows:
        pdf.set_text_color(30, 41, 59)
        if style == "rule":
            pdf.set_draw_color(203, 213, 225)
            y = pdf.get_y() + 1
            pdf.line(pdf.l_margin, y, pdf.l_margin + width, y)
            pdf.ln(2.5)
            continue
        if style == "title":
            pdf.set_font("Noto", "B", 10)
            pdf.set_text_color(*NAVY)
            pdf.cell(width - value_w, 6, label)
            pdf.set_font("Noto", "", 8)
            pdf.cell(value_w, 6, value, align="R", new_x="LMARGIN", new_y="NEXT")
            continue
        size = 7.5 if style == "small" else 8.5
        pdf.set_font("Noto", "B" if style == "B" else "", size)
        if style == "small":
            pdf.set_text_color(*GREY)
        if not label:  # value-only row (continuation)
            pdf.multi_cell(width, 4, value, new_x="LMARGIN", new_y="NEXT")
            continue
        if label in ("Patient", "Doctor", "Visit", "Reason", "Date"):
            pdf.multi_cell(width, 4.4, f"{label}: {value}", new_x="LMARGIN", new_y="NEXT")
            continue
        height = pdf.multi_cell(width - value_w, 4.4, label, dry_run=True, output="HEIGHT")
        if not thermal and pdf.get_y() + height > pdf.page_break_trigger:
            pdf.add_page()
        y = pdf.get_y()
        pdf.multi_cell(width - value_w, 4.4, label, new_x="RIGHT", new_y="TOP")
        pdf.set_xy(pdf.l_margin + width - value_w, y)
        pdf.cell(value_w, 4.4, value, align="R")
        pdf.set_xy(pdf.l_margin, y + max(height, 4.4))

    pdf.ln(3)
    pdf.set_font("Noto", "", 7)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(width, 3.6, "Computer-generated receipt. Thank you." if thermal else
                   "This is a computer-generated receipt and does not need a signature. Please keep it for your records.",
                   align="C" if thermal else "L", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
