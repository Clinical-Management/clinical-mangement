"""Render a report as page images. The same images are sent to the AI and shown in the
side-by-side viewer, so locations the AI reports line up with what the doctor sees."""

import io
import logging
from functools import lru_cache

import numpy as np
from PIL import Image

from app.reports.files import load_image

log = logging.getLogger(__name__)

LONG_SIDE = 1568  # px: large enough to read small print, within the AI's image size sweet spot
MAX_PAGES = 10


def _png(img: Image.Image) -> bytes:
    img = img.convert("RGB")
    img.thumbnail((LONG_SIDE, LONG_SIDE))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def dicom_to_image(data: bytes) -> Image.Image | None:
    """DICOM pixel data -> 8-bit image (windowed to the 0.5-99.5 percentile), or None if undecodable."""
    import pydicom

    try:
        ds = pydicom.dcmread(io.BytesIO(data))
        pixels = ds.pixel_array.astype(np.float32)
        if pixels.ndim == 3 and pixels.shape[-1] not in (3, 4):
            pixels = pixels[pixels.shape[0] // 2]  # multi-frame: middle slice
        lo, hi = np.percentile(pixels, (0.5, 99.5))
        pixels = np.clip((pixels - lo) / max(hi - lo, 1) * 255, 0, 255).astype(np.uint8)
        if str(ds.get("PhotometricInterpretation", "")) == "MONOCHROME1":
            pixels = 255 - pixels
        return Image.fromarray(pixels)
    except Exception:
        log.info("DICOM pixel data could not be decoded", exc_info=True)
        return None


def render_pages(kind: str, data: bytes) -> list[bytes]:
    """PNG bytes per page (at most MAX_PAGES). Empty list if nothing can be rendered."""
    if kind == "pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        pages = []
        for i in range(min(len(pdf), MAX_PAGES)):
            page = pdf[i]
            scale = LONG_SIDE / max(page.get_size())
            pages.append(_png(page.render(scale=scale).to_pil()))
        return pages
    if kind == "dicom":
        img = dicom_to_image(data)
        return [_png(img)] if img else []
    return [_png(load_image(data))]


@lru_cache(maxsize=64)
def cached_pages(file_key: str, kind: str, data: bytes) -> tuple[bytes, ...]:
    """Rendering PDFs is the slow part; keep recent ones (keyed by stored file id)."""
    return tuple(render_pages(kind, data))
