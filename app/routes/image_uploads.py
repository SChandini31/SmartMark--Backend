import hashlib
import uuid
from pathlib import Path
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.services.ocr_service import extract_image_text
from app.services.embedding_service import generate_embedding

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.resource import Resource
from app.models.user import User


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/images",
    tags=["Images"],
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = (BACKEND_ROOT / "uploads" / "images").resolve()
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

ALLOWED_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def delete_stored_file(path: Path | None) -> None:
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def has_valid_signature(extension: str, content: bytes) -> bool:
    if extension in {".jpg", ".jpeg"}:
        return content.startswith(b"\xFF\xD8\xFF")

    if extension == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")

    if extension == ".webp":
        return (
            len(content) >= 12
            and content.startswith(b"RIFF")
            and content[8:12] == b"WEBP"
        )

    return False


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stored_path = None
    content = b""
    file_hash = None

    try:
        # 1. Validate the original filename.
        original_filename = Path(file.filename or "").name

        if not original_filename:
            raise HTTPException(
                status_code=400,
                detail="A filename is required.",
            )

        extension = Path(original_filename).suffix.lower()

        if extension not in ALLOWED_TYPES:
            raise HTTPException(
                status_code=415,
                detail="Unsupported image format. Use JPG, JPEG, PNG, or WebP.",
            )

        expected_mime = ALLOWED_TYPES[extension]
        supplied_mime = (file.content_type or "").lower()

        if supplied_mime not in {
            expected_mime,
            "application/octet-stream",
        }:
            raise HTTPException(
                status_code=415,
                detail="The uploaded MIME type does not match the image format.",
            )

        # 2. Read only up to the limit plus one byte.
        content = await file.read(MAX_FILE_SIZE + 1)

        if not content:
            raise HTTPException(
                status_code=400,
                detail="The uploaded image is empty.",
            )

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Image exceeds the 10 MB upload limit.",
            )

        # 3. Validate the file's basic signature.
        if not has_valid_signature(extension, content):
            raise HTTPException(
                status_code=415,
                detail="The file contents do not match a supported image format.",
            )

        # 4. Calculate SHA-256 to detect duplicate files.
        file_hash = hashlib.sha256(content).hexdigest()

        existing_resource = (
            db.query(Resource)
            .filter(
                Resource.user_id == current_user.id,
                Resource.file_hash == file_hash,
            )
            .first()
        )

        if existing_resource:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "This file has already been saved.",
                    "existing_resource_id": existing_resource.id,
                    "existing_resource_type": existing_resource.resource_type,
                },
            )

        # 5. Store the image using a server-generated filename.
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        stored_path = (
            UPLOAD_DIR / f"{uuid.uuid4().hex}{extension}"
        ).resolve()

        if stored_path.parent != UPLOAD_DIR:
            raise HTTPException(
                status_code=400,
                detail="Invalid storage path.",
            )

        stored_path.write_bytes(content)


        # 6. Extract text from the image using OCR.
        extracted_text = None
        extraction_status = "failed"
        ocr_message = "Image uploaded, but OCR failed."

        try:
            extracted_text = extract_image_text(str(stored_path))

            if extracted_text:
                extraction_status = "completed"
                ocr_message = "Text extracted successfully."
            else:
                extraction_status = "no_text"
                ocr_message = "No text detected in the image."

        except Exception:
            logger.exception("OCR failed for image: %s", original_filename)

            extracted_text = None
            extraction_status = "failed"
            ocr_message = "Image uploaded, but OCR failed. Check backend logs."
        # Generate an embedding from the extracted OCR text.
        embedding = None

        if extracted_text and extracted_text.strip():
            try:
                embedding = generate_embedding(extracted_text)
            except Exception:
                logger.exception(
                 "Embedding generation failed for image: %s",
                    original_filename,
            )
        # 7. Save image metadata and extracted text.
        resource = Resource(
            user_id=current_user.id,
            url=None,
            title=original_filename,
            resource_type="image",
            original_filename=original_filename,
            file_path=str(stored_path),
            mime_type=expected_mime,
            file_hash=file_hash,
            extracted_text=extracted_text,
            extraction_status=extraction_status,
            embedding=embedding,
        )

        db.add(resource)
        db.commit()
        db.refresh(resource)

        return {
            "message": "Image uploaded successfully.",
            "resource_id": resource.id,
            "filename": original_filename,
            "mime_type": expected_mime,
            "resource_type": resource.resource_type,
            "extraction_status": resource.extraction_status,
            "ocr": ocr_message,
            "extracted_text": resource.extracted_text,
        }

    except HTTPException:
        db.rollback()
        delete_stored_file(stored_path)
        raise

    except IntegrityError:
        db.rollback()
        delete_stored_file(stored_path)

        # Check whether a concurrent request saved the same file.
        existing_resource = None

        if file_hash:
            existing_resource = (
                db.query(Resource)
                .filter(
                    Resource.user_id == current_user.id,
                    Resource.file_hash == file_hash,
                )
                .first()
            )

        if existing_resource:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "This file has already been saved.",
                    "existing_resource_id": existing_resource.id,
                    "existing_resource_type": existing_resource.resource_type,
                },
            )

        raise HTTPException(
            status_code=500,
            detail="Could not save image metadata.",
        )

    except Exception:
        db.rollback()
        delete_stored_file(stored_path)

        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while uploading the image.",
        )

    finally:
        await file.close()
