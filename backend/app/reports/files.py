"""Report file checks: type (by content, not extension), size, readability, and image quality.

Errors reject the upload; warnings (blur, skew, low resolution) are shown to the
uploader, who can retake the photo or upload anyway.
"""

import io
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

KINDS = {
    "pdf": "application/pdf",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "dicom": "application/dicom",
}

MIN_SIDE_ERROR = 300  # px: below this, text is unreadable
MIN_SIDE_WARN = 1000  # px: small print may be hard to read
BLUR_WARN = 80.0  # variance of the Laplacian on a ~1000 px greyscale copy
SKEW_WARN = 3.0  # degrees


@dataclass
class FileCheck:
    kind: str | None = None
    content_type: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def sniff(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) > 132 and data[128:132] == b"DICM":
        return "dicom"
    return None


def check_file(data: bytes, filename: str, max_mb: int) -> FileCheck:
    result = FileCheck()
    size_mb = len(data) / 1024 / 1024
    result.info["size_bytes"] = len(data)
    if not data:
        result.errors.append("The file is empty.")
        return result
    if size_mb > max_mb:
        result.errors.append(f"The file is {size_mb:.1f} MB; the limit is {max_mb} MB.")
        return result

    kind = sniff(data)
    if kind is None:
        result.errors.append(
            f'"{filename}" is not a supported file. Upload a PDF, a JPG/PNG photo or scan, or a DICOM (.dcm) file.'
        )
        return result
    result.kind, result.content_type = kind, KINDS[kind]

    if kind == "pdf":
        _check_pdf(data, result)
    elif kind == "dicom":
        _check_dicom(data, result)
    else:
        _check_image(data, result)
    return result


def _check_pdf(data: bytes, result: FileCheck) -> None:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            result.errors.append("This PDF is password-protected. Please upload an unlocked copy.")
            return
        pages = len(reader.pages)
    except (PdfReadError, ValueError, KeyError, OSError):
        result.errors.append("This PDF appears to be damaged and cannot be opened.")
        return
    if pages == 0:
        result.errors.append("This PDF has no pages.")
    result.info["pages"] = pages


def _check_dicom(data: bytes, result: FileCheck) -> None:
    import pydicom  # imported lazily: only needed for DICOM uploads

    try:
        ds = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)
    except Exception:  # pydicom raises a variety of errors on corrupt files
        result.errors.append("This DICOM file appears to be damaged and cannot be read.")
        return
    result.info.update(
        {
            "modality": str(ds.get("Modality", "")) or None,
            "study_date": str(ds.get("StudyDate", "")) or None,
            "body_part": str(ds.get("BodyPartExamined", "")) or None,
            "study_description": str(ds.get("StudyDescription", "")) or None,
        }
    )


def load_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    return ImageOps.exif_transpose(img)  # respect phone camera orientation


def _check_image(data: bytes, result: FileCheck) -> None:
    try:
        img = load_image(data)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        result.errors.append("This image appears to be damaged and cannot be opened.")
        return

    w, h = img.size
    result.info.update({"width": w, "height": h})
    short = min(w, h)
    if short < MIN_SIDE_ERROR:
        result.errors.append(f"The image is too small to read ({w}x{h} px). Please retake it closer or scan it.")
        return
    if short < MIN_SIDE_WARN:
        result.warnings.append(f"Low resolution ({w}x{h} px): small print may be hard to read.")

    grey = img.convert("L")
    grey.thumbnail((1000, 1000))
    pixels = np.asarray(grey, dtype=np.float32)

    blur = laplacian_variance(pixels)
    result.info["sharpness"] = round(blur, 1)
    if blur < BLUR_WARN:
        result.warnings.append("The image looks blurry. Hold the phone steady and make sure the text is in focus.")

    skew = estimate_skew(grey)
    result.info["skew_degrees"] = skew
    if abs(skew) >= SKEW_WARN:
        result.warnings.append(f"The page looks tilted by about {abs(skew):.0f}°. Try to photograph it straight on.")


def laplacian_variance(pixels: np.ndarray) -> float:
    lap = (
        pixels[:-2, 1:-1] + pixels[2:, 1:-1] + pixels[1:-1, :-2] + pixels[1:-1, 2:] - 4 * pixels[1:-1, 1:-1]
    )
    return float(lap.var())


def _otsu(arr: np.ndarray) -> float:
    hist, _ = np.histogram(arr, bins=256, range=(0, 256))
    total, levels = arr.size, np.arange(256)
    w0 = np.cumsum(hist)
    m0 = np.cumsum(hist * levels)
    w1 = total - w0
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (m0[-1] * w0 / total - m0) ** 2 / (w0 * w1)
    return float(np.nanargmax(between))


def estimate_skew(grey: Image.Image, max_angle: float = 15.0, step: float = 1.0) -> float:
    """Angle (degrees) that makes text lines most horizontal: maximises the variance of the
    row-wise ink profile. Returns 0 for images without enough text-like content."""
    small = grey.copy()
    small.thumbnail((600, 600))
    arr = np.asarray(small, dtype=np.float32)

    # Photos often show the table around the page: measure only inside the paper's central area
    paper = arr > _otsu(arr)
    ys, xs = np.nonzero(paper)
    if len(ys) > arr.size * 0.15:
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        dy, dx = (y1 - y0) // 5, (x1 - x0) // 5
        arr = arr[y0 + dy : y1 - dy, x0 + dx : x1 - dx]
    if arr.size < 2500:
        return 0.0
    ink = (arr < np.median(arr) - max(arr.std(), 10)).astype(np.uint8) * 255
    if ink.mean() < 2:  # almost no dark content
        return 0.0
    ink_img = Image.fromarray(ink)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + step / 2, step):
        rotated = np.asarray(ink_img.rotate(float(angle), resample=Image.Resampling.NEAREST, fillcolor=0), dtype=np.float32)
        score = float(rotated.sum(axis=1).var())
        if score > best_score:
            best_angle, best_score = float(angle), score
    # rotating by +a straightens a page skewed by -a
    return round(-best_angle, 1) + 0.0  # + 0.0 turns -0.0 into 0.0
