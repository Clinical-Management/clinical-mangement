"""Build a shareable PDF from one or more reports: a cover page per report, then its content.

Originals are never modified: content pages are copied from the stored file
(PDF pages as-is; images and DICOM rendered onto PDF pages).
"""

import io
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter

from app.reports.files import load_image
from app.reports.pages import dicom_to_image

A4 = (1240, 1754)  # A4 at 150 dpi
NAVY = (2, 59, 119)
TEAL = (3, 149, 131)


def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _page_pdf(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PDF", resolution=150)
    return buf.getvalue()


def cover_page(lines: list[tuple[str, str]], title: str) -> bytes:
    img = Image.new("RGB", A4, "white")
    d = ImageDraw.Draw(img)
    # brand gradient header
    for x in range(A4[0]):
        t = x / A4[0]
        d.line([(x, 0), (x, 160)], fill=tuple(int(NAVY[i] + (TEAL[i] - NAVY[i]) * t) for i in range(3)))
    d.text((90, 52), "Clinical Management", font=_font(44), fill="white")
    d.text((90, 240), title, font=_font(52), fill=(30, 41, 59))
    y = 360
    for label, value in lines:
        d.text((90, y), label, font=_font(26), fill=(100, 116, 139))
        d.text((420, y), value or "-", font=_font(30), fill=(30, 41, 59))
        y += 62
    d.text(
        (90, A4[1] - 110),
        f"Exported {datetime.now().strftime('%d %b %Y %H:%M')}. Copy of the stored original; the original is unchanged.",
        font=_font(22),
        fill=(100, 116, 139),
    )
    return _page_pdf(img)


def message_page(text: str) -> bytes:
    img = Image.new("RGB", A4, "white")
    ImageDraw.Draw(img).multiline_text((90, 300), text, font=_font(32), fill=(30, 41, 59), spacing=14)
    return _page_pdf(img)


def image_pages(data: bytes) -> bytes:
    img = load_image(data).convert("RGB")
    img.thumbnail((A4[0] - 120, A4[1] - 120))  # keep a margin; never upscale
    page = Image.new("RGB", A4, "white")
    page.paste(img, ((A4[0] - img.width) // 2, (A4[1] - img.height) // 2))
    return _page_pdf(page)


def dicom_pages(data: bytes) -> bytes:
    """Render the DICOM pixel data when it is uncompressed or uses a codec pydicom handles natively."""
    img = dicom_to_image(data)
    if img is None:
        return message_page(
            "This DICOM image could not be rendered into the PDF.\n"
            "Please download the original .dcm file\n"
            "and open it in a DICOM viewer."
        )
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return image_pages(buf.getvalue())


def build_pdf(parts: list[dict]) -> bytes:
    """parts: [{"title", "lines": [(label, value)], "kind", "data"}] -> one merged PDF."""
    writer = PdfWriter()
    for part in parts:
        writer.append(PdfReader(io.BytesIO(cover_page(part["lines"], part["title"]))))
        if part["kind"] == "pdf":
            content = part["data"]
        elif part["kind"] == "dicom":
            content = dicom_pages(part["data"])
        else:
            content = image_pages(part["data"])
        writer.append(PdfReader(io.BytesIO(content)))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
