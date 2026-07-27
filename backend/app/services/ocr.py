"""OCR service — extract text from scanned images and PDFs using Tesseract."""

import logging
import tempfile
from io import BytesIO
from pathlib import Path

import pytesseract
from PIL import Image
from pdf2image import convert_from_bytes
from pypdf import PdfReader

from app.config import settings

logger = logging.getLogger(__name__)


def _set_tesseract_cmd() -> None:
    """Set the tesseract command path if configured."""
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


_set_tesseract_cmd()


async def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF using PyPDF (fast path) with OCR fallback."""
    text_parts: list[str] = []

    # Try PyPDF extraction first
    try:
        reader = PdfReader(BytesIO(file_bytes))
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)

        joined = "".join(text_parts).strip()
        # If we got meaningful text, return it
        if len(joined) > 50:
            return joined
    except Exception as e:
        logger.warning("PyPDF extraction failed: %s. Falling back to OCR.", e)

    # Fallback: OCR with pdf2image + tesseract
    logger.info("Performing OCR on PDF (%d bytes)...", len(file_bytes))
    try:
        images = convert_from_bytes(file_bytes, dpi=300)
        ocr_parts: list[str] = []
        for i, img in enumerate(images):
            text = pytesseract.image_to_string(img)
            ocr_parts.append(f"--- Page {i + 1} ---\n{text}")
        return "\n\n".join(ocr_parts)
    except Exception as e:
        logger.error("PDF OCR failed: %s", e)
        return ""


async def extract_text_from_image(file_bytes: bytes) -> str:
    """Extract text from an image using Tesseract OCR."""
    try:
        img = Image.open(BytesIO(file_bytes))
        text = pytesseract.image_to_string(img)
        return text.strip()
    except Exception as e:
        logger.error("Image OCR failed: %s", e)
        return ""


async def extract_text(filename: str, file_bytes: bytes) -> str:
    """Extract text from a file, choosing the right method based on extension."""
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        return await extract_text_from_pdf(file_bytes)
    elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"):
        return await extract_text_from_image(file_bytes)
    elif ext == ".txt":
        return file_bytes.decode("utf-8", errors="replace")
    elif ext == ".eml":
        # Basic .eml text extraction — will be improved in Phase 2
        try:
            return file_bytes.decode("utf-8", errors="replace")
        except Exception:
            return file_bytes.decode("latin-1", errors="replace")
    else:
        # Fallback: try as text
        try:
            return file_bytes.decode("utf-8", errors="replace")
        except Exception:
            return ""


async def count_pages(filename: str, file_bytes: bytes) -> int:
    """Count pages in a document."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        try:
            reader = PdfReader(BytesIO(file_bytes))
            return len(reader.pages)
        except Exception:
            return 1
    elif ext in (".tiff", ".tif"):
        try:
            img = Image.open(BytesIO(file_bytes))
            return getattr(img, "n_frames", 1)
        except Exception:
            return 1
    else:
        return 1
