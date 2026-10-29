import re
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

# Configure the installed Tesseract executable.
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# Images smaller than this (longest side, in pixels) are upscaled before OCR.
OCR_MIN_IMAGE_SIDE = 2000

_CLEAN_WORD = re.compile(r"[A-Za-z]{3,}[.,;:]?")


def _clean_word_count(text: str) -> int:
    return sum(1 for t in (text or "").split() if _CLEAN_WORD.fullmatch(t))


def _prepare_for_ocr(image: Image.Image) -> Image.Image:
    """Grayscale, upscale small images and boost contrast."""
    image = image.convert("L")
    width, height = image.size

    if max(width, height) < OCR_MIN_IMAGE_SIDE:
        image = image.resize((width * 2, height * 2), Image.LANCZOS)

    return ImageOps.autocontrast(image)


def ocr_image(image: Image.Image) -> str:
    """
    OCR a PIL image with preprocessing.

    Tries a block layout (psm 6) and a sparse-text layout (psm 11,
    better for screenshots) and keeps whichever gives more readable words.
    """
    prepared = _prepare_for_ocr(image)

    best_text = ""
    best_count = -1

    for psm in (6, 11):
        try:
            text = pytesseract.image_to_string(
                prepared,
                config=f"--psm {psm}",
            ).strip()
        except pytesseract.TesseractNotFoundError:
            # Don't hide a missing Tesseract install as "no text found".
            raise
        except Exception:
            continue

        count = _clean_word_count(text)

        if count > best_count:
            best_text = text
            best_count = count

    return best_text


def extract_image_text(image_path: str) -> str:
    path = Path(image_path)

    with Image.open(path) as image:
        image.load()
        return ocr_image(image.convert("RGB"))