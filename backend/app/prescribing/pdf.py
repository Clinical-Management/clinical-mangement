"""Prescription PDF on the clinic letterhead (fpdf2 with HarfBuzz shaping for Devanagari)."""

import io
from datetime import date, datetime
from pathlib import Path

import qrcode
from fpdf import FPDF
from fpdf.fonts import FontFace

from app.prescribing import translate as tr

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
NAVY = (2, 59, 119)
TEAL = (3, 149, 131)
GREY = (100, 116, 139)
RED = (185, 28, 28)


class _PDF(FPDF):
    def __init__(self, footer_text: str):
        super().__init__(format="A4")
        self.footer_text = footer_text
        self.add_font("Noto", "", str(FONTS / "NotoSans-Regular.ttf"))
        self.add_font("Noto", "B", str(FONTS / "NotoSans-Bold.ttf"))
        self.add_font("NotoDeva", "", str(FONTS / "NotoSansDevanagari-Regular.ttf"))
        self.add_font("NotoDeva", "B", str(FONTS / "NotoSansDevanagari-Bold.ttf"))
        self.set_fallback_fonts(["NotoDeva"])
        self.set_text_shaping(True)
        self.set_auto_page_break(True, margin=18)
        self.set_margins(14, 12, 14)

    def footer(self):
        self.set_y(-12)
        self.set_font("Noto", "", 7.5)
        self.set_text_color(*GREY)
        self.cell(0, 5, f"{self.footer_text}    {self.page_no()}/{{nb}}", align="C")


def _fmt_date(value) -> str:
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            return value
    return value.strftime("%d %b %Y") if isinstance(value, (date, datetime)) else ""


def _qr_png(url: str) -> io.BytesIO:
    img = qrcode.make(url, box_size=6, border=1)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


def render(version: dict, *, lang: str = "en", copy: str = "clinic", translations: dict[str, str] | None = None,
           signature_png: bytes | None = None, verify_url: str) -> bytes:
    """version: a finalized prescription version (content + letterhead + patient snapshot)."""
    t = tr.LABELS[lang]
    tx = translations or {}
    def say(text):  # free text in the patient's language when a translation exists
        return tx.get(text, text) if text else text

    c, head, patient = version["content"], version["letterhead"], version["patient"]
    pdf = _PDF(f"{version['public_id']} | {t['version']} {version['version']} | {t['signed']} {_fmt_date(version['finalized_at'])}")
    pdf.alias_nb_pages()
    pdf.add_page()

    # --- letterhead ---
    top = pdf.get_y()
    pdf.set_text_color(*NAVY)
    pdf.set_font("Noto", "B", 16)
    pdf.cell(110, 8, head["clinic_name"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Noto", "", 8.5)
    pdf.set_text_color(*GREY)
    for line in filter(None, [head.get("address"), " | ".join(filter(None, [head.get("phone"), head.get("email")])),
                              head.get("clinic_registration") and f"Clinic reg.: {head['clinic_registration']}"]):
        pdf.multi_cell(110, 4.2, line, new_x="LMARGIN", new_y="NEXT")
    left_bottom = pdf.get_y()
    pdf.set_xy(124, top)
    pdf.set_text_color(30, 41, 59)
    pdf.set_font("Noto", "B", 12)
    pdf.multi_cell(72, 6, head["doctor_name"], align="R", new_x="LEFT", new_y="NEXT")
    pdf.set_font("Noto", "", 8.5)
    pdf.set_text_color(*GREY)
    for line in filter(None, [head.get("qualifications"), head.get("specialization"),
                              head.get("registration_number") and f"{t['registration']} {head['registration_number']}"
                              + (f" ({head['registration_council']})" if head.get("registration_council") else "")]):
        pdf.multi_cell(72, 4.2, line, align="R", new_x="LEFT", new_y="NEXT")
    y = max(left_bottom, pdf.get_y()) + 2
    pdf.set_draw_color(*TEAL)
    pdf.set_line_width(0.9)
    pdf.line(14, y, 196, y)
    pdf.set_y(y + 3)

    # --- patient ---
    pdf.set_text_color(30, 41, 59)
    pdf.set_font("Noto", "B", 10)
    gender = tr.GENDERS.get(lang, {}).get(patient["gender"], patient["gender"].replace("_", " "))
    pdf.cell(120, 5.5, f"{t['patient']}: {patient['name']} ({patient['age'] if patient['age'] is not None else '?'} y, {gender})")
    pdf.set_font("Noto", "", 9)
    pdf.cell(0, 5.5, f"{t['date']}: {_fmt_date(version['visit_date'])}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(120, 5, f"{t['patient_id']}: {patient['patient_id']}")
    if copy == "patient":
        pdf.cell(0, 5, t["patient_copy"], align="R")
    pdf.ln(5)
    pdf.set_text_color(*RED)
    pdf.set_font("Noto", "B", 9)
    pdf.multi_cell(0, 5, f"{t['allergies']}: {', '.join(patient['allergies']) if patient['allergies'] else t['none_known']}",
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    def heading(text):
        pdf.set_font("Noto", "B", 8.5)
        pdf.set_text_color(*GREY)
        pdf.cell(0, 5, text.upper() if lang == "en" else text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(30, 41, 59)
        pdf.set_font("Noto", "", 9.5)

    # --- case summary ---
    for section in version["case_summary"]:
        heading(tr.SECTION_TITLES.get(lang, {}).get(section["key"], section["title"]))
        pdf.multi_cell(0, 4.8, say(section["text"]), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(0.8)

    # --- Rx ---
    pdf.ln(1)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Noto", "B", 18)
    pdf.cell(0, 9, "℞", new_x="LMARGIN", new_y="NEXT")
    if c["medicines"]:
        pdf.set_draw_color(203, 213, 225)
        pdf.set_line_width(0.2)
        pdf.set_font("Noto", "", 9)
        pdf.set_text_color(30, 41, 59)
        headings = ["#", t["medicine"], t["dose"], t["how_often"], t["how_long"], t["instructions"]]
        with pdf.table(col_widths=(6, 52, 20, 40, 22, 42), headings_style=FontFace(emphasis="BOLD", color=GREY),
                       line_height=5, padding=1.2, borders_layout="HORIZONTAL_LINES", first_row_as_headings=True) as table:
            row = table.row()
            for h in headings:
                row.cell(h)
            for i, m in enumerate(c["medicines"], start=1):
                row = table.row()
                row.cell(str(i))
                sub = " / ".join(filter(None, [m.get("generic") if m.get("generic") and m["generic"] != m["name"] else None, m.get("route")]))
                row.cell(m["name"] + (f"\n{sub}" if sub else ""))
                row.cell(m.get("dose") or "")
                row.cell(tr.frequency(m.get("frequency"), lang))
                row.cell(tr.duration(m.get("duration"), lang))
                instr = m.get("instructions")
                row.cell((tr.phrase(instr, lang) or say(instr) or "") if instr else "")
    pdf.ln(2)

    def block(title, text):
        if text:
            heading(title)
            pdf.multi_cell(0, 4.8, text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

    block(t["investigations"], ", ".join(i["name"] + (f" ({say(i['notes'])})" if i.get("notes") else "") for i in c["investigations"]))
    block(t["advice"], say(c.get("advice")))
    block(t["diet"], say(c.get("diet_lifestyle")))
    ref = c.get("referral")
    if ref and ref.get("to"):
        block(t["referral"], " - ".join(filter(None, [ref["to"], ref.get("specialty"), say(ref.get("notes"))])))
    fu = c.get("follow_up")
    if fu and (fu.get("date") or fu.get("note")):
        block(t["follow_up"], " - ".join(filter(None, [_fmt_date(fu.get("date")), say(fu.get("note"))])))
    if lang != "en" and t["translated_note"]:
        pdf.set_font("Noto", "", 8)
        pdf.set_text_color(*GREY)
        pdf.multi_cell(0, 4, t["translated_note"], new_x="LMARGIN", new_y="NEXT")

    # --- verification + signature (kept together at the bottom) ---
    if pdf.get_y() > 240:
        pdf.add_page()
    y = max(pdf.get_y() + 6, 238)
    pdf.image(_qr_png(verify_url), x=14, y=y, w=28)
    pdf.set_xy(44, y + 4)
    pdf.set_font("Noto", "B", 8.5)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(70, 4.5, t["verify"], new_x="LEFT", new_y="NEXT")
    pdf.set_font("Noto", "", 8)
    pdf.set_text_color(*GREY)
    pdf.cell(70, 4.2, version["public_id"], new_x="LEFT", new_y="NEXT")
    pdf.cell(70, 4.2, f"{t['version']} {version['version']} | {t['signed']} {_fmt_date(version['finalized_at'])}", new_x="LEFT", new_y="NEXT")
    if signature_png:
        pdf.image(io.BytesIO(signature_png), x=140, y=y, h=16, keep_aspect_ratio=True)
    pdf.set_xy(124, y + 18)
    pdf.set_draw_color(*GREY)
    pdf.set_line_width(0.2)
    pdf.line(130, y + 18, 196, y + 18)
    pdf.set_font("Noto", "B", 9)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(72, 5, head["doctor_name"], align="R", new_x="LEFT", new_y="NEXT")
    if head.get("registration_number"):
        pdf.set_font("Noto", "", 8)
        pdf.cell(72, 4, f"{t['registration']} {head['registration_number']}", align="R")
    return bytes(pdf.output())
