import io

import numpy as np
from PIL import Image, ImageDraw
from pypdf import PdfReader

from app.core.config import settings
from tests.test_appointments import book, clinic, now  # noqa: F401
from tests.test_patients import patient_payload


def pdf_bytes(pages=1) -> bytes:
    imgs = [Image.new("RGB", (1240, 1754), "white") for _ in range(pages)]
    buf = io.BytesIO()
    imgs[0].save(buf, "PDF", save_all=True, append_images=imgs[1:])
    return buf.getvalue()


def photo_bytes(size=(1600, 2200)) -> bytes:
    img = Image.new("L", size, 255)
    d = ImageDraw.Draw(img)
    for y in range(150, size[1] - 150, 60):
        d.rectangle([150, y, size[0] - 150, y + 18], fill=20)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG")
    return buf.getvalue()


def dicom_bytes() -> bytes:
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.Modality, ds.StudyDate, ds.BodyPartExamined = "CR", "20300101", "CHEST"
    ds.Rows, ds.Columns, ds.SamplesPerPixel, ds.PhotometricInterpretation = 64, 64, 1, "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
    ds.PixelData = (np.arange(64 * 64, dtype=np.uint16).reshape(64, 64) % 4096).tobytes()
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    return buf.getvalue()


def upload(client, c, data, name="report.pdf", headers=None, pid=None, **form):
    fields = {"report_type": "blood_test", "report_date": "2030-01-05", "ordering_doctor": "Dr Mehta", **form}
    files = {"file": (name, data)}
    if "processed" in fields:
        files["processed"] = ("enhanced.jpg", fields.pop("processed"))
    return client.post(f"/api/v1/patients/{pid or c['pid']}/reports", data=fields, files=files, headers=headers or c["doctor"])


def test_upload_pdf_photo_and_dicom(client, clinic):
    r = upload(client, clinic, pdf_bytes(2))
    assert r.status_code == 201, r.text
    assert r.json()["versions"][0]["info"]["pages"] == 2

    r = upload(client, clinic, photo_bytes(), name="cbc.jpg", source="camera", processed=photo_bytes())
    v = r.json()["versions"][0]
    assert v["kind"] == "jpeg" and v["has_processed"] and v["source"] == "camera" and v["warnings"] == []

    r = upload(client, clinic, dicom_bytes(), name="chest.dcm", report_type="xray")
    assert r.json()["versions"][0]["info"]["modality"] == "CR"


def test_validation_errors_and_warnings(client, clinic, monkeypatch):
    url = f"/api/v1/patients/{clinic['pid']}/reports"
    r = upload(client, clinic, b"PK\x03\x04 not a report", name="report.docx")
    assert r.status_code == 422 and "not a supported file" in r.json()["detail"]
    assert upload(client, clinic, b"%PDF-1.4 broken").json()["detail"].startswith("This PDF appears to be damaged")

    # required tags
    r = client.post(url, data={"report_type": "xray", "report_date": "2030-01-05"}, files={"file": ("a.pdf", pdf_bytes())}, headers=clinic["doctor"])
    assert r.status_code == 422
    assert upload(client, clinic, pdf_bytes(), report_date="2031-01-01").status_code == 422  # future date
    assert upload(client, clinic, pdf_bytes(), report_type="blood").status_code == 422

    monkeypatch.setattr(settings, "report_max_mb", 0)
    assert "limit is 0 MB" in upload(client, clinic, pdf_bytes()).json()["detail"]
    monkeypatch.setattr(settings, "report_max_mb", 25)

    # dry-run check: quality warnings and duplicates
    small = photo_bytes((700, 900))
    r = client.post(f"{url}/check", files={"file": ("small.jpg", small)}, headers=clinic["desk"]).json()
    assert r["ok"] and any("Low resolution" in w for w in r["warnings"])
    first = upload(client, clinic, small, name="small.jpg").json()
    r = client.post(f"{url}/check", files={"file": ("again.jpg", small)}, headers=clinic["desk"]).json()
    assert r["duplicate_of"] == first["id"]


def test_versions_keep_originals(client, clinic):
    original = pdf_bytes(1)
    report = upload(client, clinic, original).json()
    url = f"/api/v1/reports/{report['id']}"
    r = client.post(f"{url}/versions", data={"reason": "Clearer scan"}, files={"file": ("v2.pdf", pdf_bytes(3))}, headers=clinic["doctor"])
    assert r.json()["current_version"] == 2 and r.json()["versions"][1]["reason"] == "Clearer scan"
    assert client.post(f"{url}/versions", files={"file": ("v3.pdf", pdf_bytes())}, headers=clinic["doctor"]).status_code == 422

    v1 = client.get(f"{url}/file", params={"version": 1}, headers=clinic["doctor"]).content
    latest = client.get(f"{url}/file", headers=clinic["doctor"]).content
    assert len(PdfReader(io.BytesIO(v1)).pages) == 1 and len(PdfReader(io.BytesIO(latest)).pages) == 3
    assert v1 == original  # byte-for-byte the uploaded original


def test_library_filters_and_metadata_edit(client, clinic):
    appt = book(client, clinic).json()["id"]
    upload(client, clinic, pdf_bytes(), report_type="ecg", report_date="2029-06-01")
    upload(client, clinic, pdf_bytes(2), report_type="xray", report_date="2030-01-02", appointment_id=appt)
    base = f"/api/v1/patients/{clinic['pid']}/reports"
    assert [r["report_type"] for r in client.get(base, headers=clinic["doctor"]).json()] == ["xray", "ecg"]
    assert [r["report_type"] for r in client.get(base, params={"report_type": "ecg"}, headers=clinic["doctor"]).json()] == ["ecg"]
    assert len(client.get(base, params={"date_from": "2030-01-01"}, headers=clinic["doctor"]).json()) == 1
    visit = client.get(base, params={"appointment_id": appt}, headers=clinic["doctor"]).json()
    assert len(visit) == 1 and visit[0]["visit_date"] == "2030-01-07"

    r = client.patch(f"/api/v1/reports/{visit[0]['id']}", json={"report_type": "ct", "ordering_doctor": "Dr Shah"}, headers=clinic["doctor"])
    assert r.json()["report_type"] == "ct" and r.json()["current_version"] == 1


def test_access_rules(client, clinic, make_user):
    report = upload(client, clinic, pdf_bytes(), headers=clinic["desk"]).json()  # front desk uploads
    assert report["versions"][0]["uploaded_by_role"] == "receptionist"
    # ...but cannot open clinical files
    assert client.get(f"/api/v1/reports/{report['id']}/file", headers=clinic["desk"]).status_code == 403

    owner = make_user("patient")
    pid = client.post("/api/v1/patients", json=patient_payload(relationship="self", phone="5556667777"), headers=owner).json()["patient_id"]
    mine = upload(client, clinic, photo_bytes(), name="mine.jpg", headers=owner, pid=pid).json()
    assert client.get(f"/api/v1/reports/{mine['id']}/file", headers=owner).status_code == 200
    assert client.get(f"/api/v1/reports/{report['id']}", headers=owner).status_code == 404
    assert upload(client, clinic, pdf_bytes(), headers=owner).status_code == 404  # someone else's patient


def test_export_pdf(client, clinic):
    a = upload(client, clinic, pdf_bytes(2)).json()
    b = upload(client, clinic, photo_bytes(), name="cbc.jpg", source="camera", processed=photo_bytes()).json()
    c = upload(client, clinic, dicom_bytes(), name="chest.dcm", report_type="xray").json()

    one = client.get(f"/api/v1/reports/{a['id']}/export", headers=clinic["doctor"])
    assert one.headers["content-type"] == "application/pdf"
    assert len(PdfReader(io.BytesIO(one.content)).pages) == 3  # cover + 2 pages

    r = client.post(f"/api/v1/patients/{clinic['pid']}/reports/export", json={"report_ids": [a["id"], b["id"], c["id"]]}, headers=clinic["doctor"])
    assert len(PdfReader(io.BytesIO(r.content)).pages) == 3 + 2 + 2


def test_skew_detected_on_photo_with_dark_background():
    from app.reports.files import check_file

    page = Image.new("L", (1000, 1400), 245)
    d = ImageDraw.Draw(page)
    for y in range(120, 1300, 60):
        d.rectangle([80, y, 900, y + 14], fill=30)
    tilted = page.rotate(9, expand=True, fillcolor=0)
    photo = Image.new("L", (1600, 1900), 55)  # dark table around the page
    photo.paste(tilted, (180, 170), page.point(lambda _: 255).rotate(9, expand=True, fillcolor=0))
    buf = io.BytesIO()
    photo.convert("RGB").save(buf, "JPEG")
    result = check_file(buf.getvalue(), "photo.jpg", 25)
    assert abs(result.info["skew_degrees"] - 9) <= 1.5
    assert any("tilted" in w for w in result.warnings)
