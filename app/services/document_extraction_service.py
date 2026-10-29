import io
import re
from pathlib import Path

import fitz
import pytesseract
from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from PIL import Image, ImageOps
from pypdf import PdfReader

from app.services.ocr_service import extract_image_text, ocr_image as _ocr_image


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# OCR is attempted on PDF pages with fewer than this many
# non-whitespace characters.
MIN_PAGE_TEXT_LENGTH = 20

# Text quality thresholds used to flag unreadable extractions.
MIN_TEXT_LENGTH = 200
MIN_TEXT_QUALITY = 0.4

# Images smaller than this (longest side, in pixels) are upscaled before OCR.
OCR_MIN_IMAGE_SIDE = 2000


# ---------------------------------------------------------
# Text quality
# ---------------------------------------------------------

_CLEAN_WORD = re.compile(r"[A-Za-z]{3,}[.,;:]?")


def _clean_word_count(text: str) -> int:
    return sum(1 for t in (text or "").split() if _CLEAN_WORD.fullmatch(t))


def text_quality(text: str) -> float:
    """Share of tokens that look like real words (0.0 - 1.0)."""
    tokens = (text or "").split()

    if not tokens:
        return 0.0

    return _clean_word_count(text) / len(tokens)


# ---------------------------------------------------------
# Extractors
# ---------------------------------------------------------

def _extract_pdf_text(path: Path) -> str:
    """Extract normal PDF text and OCR scanned/image-based pages."""
    reader = PdfReader(str(path))

    if reader.is_encrypted:
        raise ValueError("Password-protected PDFs are not supported.")

    extracted_pages = []

    with fitz.open(str(path)) as pdf:
        for page in pdf:
            page_text = (page.get_text("text") or "").strip()

            if len(page_text) >= MIN_PAGE_TEXT_LENGTH:
                extracted_pages.append(page_text)
                continue

            # Fall back to OCR for pages with little or no text.
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(2, 2),
                alpha=False,
            )
            image_bytes = pixmap.tobytes("png")

            try:
                with Image.open(io.BytesIO(image_bytes)) as image:
                    image.load()
                    ocr_text = _ocr_image(image.convert("RGB"))
            except Exception:
                # Preserve any text that was extracted from the page.
                ocr_text = ""

            extracted_pages.append(ocr_text or page_text)

    return "\n\n".join(text for text in extracted_pages if text.strip())


def _extract_docx_text(path: Path) -> str:
    """Extract DOCX paragraphs and tables in document order, plus OCR text."""
    document = Document(str(path))
    parts = []

    # Preserve the original order of paragraphs and tables.
    for block in document.element.body.iterchildren():
        if isinstance(block, CT_P):
            paragraph = Paragraph(block, document)

            if paragraph.text.strip():
                parts.append(paragraph.text)

        elif isinstance(block, CT_Tbl):
            table = Table(block, document)

            for row in table.rows:
                row_text = " | ".join(
                    cell.text.strip() for cell in row.cells
                )
                if row_text.strip():
                    parts.append(row_text)

    # Extract OCR text from embedded images.
    seen_images = set()

    for relationship in document.part.rels.values():
        if "image" not in relationship.reltype:
            continue

        image_bytes = relationship.target_part.blob

        # Avoid OCRing the same image more than once.
        if image_bytes in seen_images:
            continue
        seen_images.add(image_bytes)

        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.load()
                ocr_text = _ocr_image(image.convert("RGB"))

            if ocr_text:
                parts.append(ocr_text)

        except Exception:
            # An unsupported or damaged image must not stop extraction.
            continue

    return "\n".join(parts)


# ---------------------------------------------------------
# Public API
# ---------------------------------------------------------

def extract_text_from_file(file_path: str) -> str:
    """
    Extract text from PDF, DOCX, and TXT files.
    Uses OCR for scanned PDF pages and embedded DOCX images.
    """
    path = Path(file_path)
    extension = path.suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type. Upload PDF, DOCX, or TXT.")

    if not path.is_file():
        raise FileNotFoundError("The uploaded file was not found.")

    if extension == ".txt":
        text = path.read_text(encoding="utf-8-sig")
    elif extension == ".pdf":
        text = _extract_pdf_text(path)
    else:
        text = _extract_docx_text(path)

    text = text.strip()

    if not text:
        raise ValueError(
            "No readable text was found in this file, "
            "even after attempting OCR."
        )

    return text


def extract_text_with_quality(file_path: str):
    """
    Returns (text, status) where status is "completed" or
    "low_quality_text".

    Use this instead of extract_text_from_file when you want the
    extraction status to reflect how readable the text actually is.
    """
    text = extract_text_from_file(file_path)

    # Short plain-text files are legitimate; only check quality for them
    # if they contain no real words at all.
    if Path(file_path).suffix.lower() == ".txt":
        status = "completed" if text_quality(text) >= 0.2 else "low_quality_text"
        return text, status

    if len(text) < MIN_TEXT_LENGTH or text_quality(text) < MIN_TEXT_QUALITY:
        return text, "low_quality_text"

    return text, "completed"