
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.resource import Resource
from app.models.user import User


router = APIRouter(
    prefix="/api/videos",
    tags=["Videos"],
)

UPLOAD_DIR = Path("uploads/videos").resolve()
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB initially

ALLOWED_TYPES = {
    ".mp4": {"video/mp4"},
    ".webm": {"video/webm"},
    ".mov": {"video/quicktime"},
    ".mkv": {"video/x-matroska"},
}


def delete_stored_file(path: Path | None) -> None:
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


@router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stored_path = None

    try:
        # Validate the filename and extension.
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
                detail="Unsupported video format. Use MP4, WebM, MOV, or MKV.",
            )

        expected_mime = next(iter(ALLOWED_TYPES[extension]))
        supplied_mime = (file.content_type or "").lower()

        if supplied_mime not in (ALLOWED_TYPES[extension] | {"application/octet-stream"}):
            raise HTTPException(
                status_code=415,
                detail="The uploaded MIME type does not match the video format.",
            )

        # Read at most 10 MB plus one byte to detect oversized files.
        content = await file.read(MAX_FILE_SIZE + 1)

        if not content:
            raise HTTPException(
                status_code=400,
                detail="The uploaded video is empty.",
            )

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Video exceeds the 10 MB upload limit.",
            )

        # Basic container-signature validation.
        if extension in {".mp4", ".mov"}:
            valid_signature = len(content) >= 8 and content[4:8] == b"ftyp"
        else:
            # WebM and Matroska/MKV commonly use the EBML header.
            valid_signature = content.startswith(b"\x1A\x45\xDF\xA3")

        if not valid_signature:
            raise HTTPException(
                status_code=415,
                detail="The file contents do not match a supported video container.",
            )

        # Hash the file to detect duplicate uploads.
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

        # Generate a server-controlled filename.
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        stored_path = (UPLOAD_DIR / f"{uuid.uuid4().hex}{extension}").resolve()

        if stored_path.parent != UPLOAD_DIR:
            raise HTTPException(
                status_code=400,
                detail="Invalid storage path.",
            )

        stored_path.write_bytes(content)

        # Save metadata only. No transcription or content extraction.
        resource = Resource(
            user_id=current_user.id,
            url=None,
            title=original_filename,
            resource_type="video",
            original_filename=original_filename,
            file_path=str(stored_path),
            mime_type=expected_mime,
            file_hash=file_hash,
            extracted_text=None,
            extraction_status="not_applicable",
        )

        db.add(resource)
        db.commit()
        db.refresh(resource)

        return {
            "message": "Video uploaded successfully.",
            "resource_id": resource.id,
            "filename": original_filename,
            "mime_type": expected_mime,
            "resource_type": resource.resource_type,
            "extraction_status": resource.extraction_status,
            "transcription": "Not performed",
        }

    except HTTPException:
        db.rollback()
        delete_stored_file(stored_path)
        raise

    except IntegrityError:
        db.rollback()
        delete_stored_file(stored_path)

        # Handles a duplicate created by another request at the same time.
        existing_resource = (
            db.query(Resource)
            .filter(
                Resource.user_id == current_user.id,
                Resource.file_hash == (
                    hashlib.sha256(content).hexdigest()
                    if "content" in locals()
                    else None
                ),
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
            detail="Could not save video metadata.",
        )

    except Exception:
        db.rollback()
        delete_stored_file(stored_path)

        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while uploading the video.",
        )

    finally:
        await file.close()
