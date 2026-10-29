import hashlib
import uuid
from pathlib import Path
from app.services.document_chunking_service import chunk_text

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.resource import Resource
from app.models.user import User
from app.services.document_chunk_service import create_document_chunks
from app.services.document_extraction_service import (
    extract_text_from_file,
    extract_text_with_quality,
)


router = APIRouter(prefix="/api/documents", tags=["Documents"])

BACKEND_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = (BACKEND_ROOT / "uploads" / "documents").resolve()
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
    ".txt": "text/plain",
}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stored_path = None

    try:
        # 1. Validate the filename and extension.
        original_filename = Path(file.filename or "").name

        if not original_filename:
            raise HTTPException(
                status_code=400,
                detail="A filename is required.",
            )

        extension = Path(original_filename).suffix.lower()

        if extension not in ALLOWED_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Only PDF, DOCX, and TXT files are supported.",
            )

        # 2. Read the file with a size limit.
        content = await file.read(MAX_FILE_SIZE + 1)

        if not content:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Maximum file size is 10 MB.",
            )

        # 3. Validate the supplied MIME type.
        expected_mime = ALLOWED_TYPES[extension]
        supplied_mime = (file.content_type or "").lower()

        if supplied_mime and supplied_mime != expected_mime:
            raise HTTPException(
                status_code=400,
                detail="File type does not match its extension.",
            )

        # 4. Perform basic file-signature validation.
        if extension == ".pdf" and not content.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=400,
                detail="Invalid PDF file.",
            )

        if extension == ".docx" and not content.startswith(b"PK"):
            raise HTTPException(
                status_code=400,
                detail="Invalid DOCX file.",
            )

        # 5. Calculate a hash of the actual file contents.
        file_hash = hashlib.sha256(content).hexdigest()

        # 6. Check for a duplicate belonging to this user.
        existing_document = (
            db.query(Resource)
            .filter(
                Resource.user_id == current_user.id,
                Resource.file_hash == file_hash,
                Resource.resource_type == "document",
            )
            .first()
        )

        if existing_document:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "This document has already been uploaded.",
                    "existing_resource_id": existing_document.id,
                    "filename": existing_document.original_filename,
                },
            )

        # 7. Create a unique storage path.
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        stored_path = (
            UPLOAD_DIR / f"{uuid.uuid4().hex}{extension}"
        ).resolve()

        if stored_path.parent != UPLOAD_DIR:
            raise HTTPException(
                status_code=400,
                detail="Invalid file path.",
            )

        # 8. Save the file and extract its text.
        stored_path.write_bytes(content)

        extracted_text, extraction_quality_status = extract_text_with_quality(str(stored_path))

        # 9. Create the resource with its file hash.
        resource = Resource(
            user_id=current_user.id,
            url=None,
            title=original_filename,
            resource_type="document",
            original_filename=original_filename,
            file_path=str(stored_path),
            mime_type=expected_mime,
            extracted_text=extracted_text,
            extraction_status=extraction_quality_status,
            file_hash=file_hash,
        )

        db.add(resource)

        # Obtain the resource ID and execute pending inserts.
        # The database unique constraint also protects against
        # concurrent duplicate uploads.
        db.flush()

        
    
        # 10. Test the new chunking logic.
        test_chunks = chunk_text(extracted_text)

        print("\n===== CHUNKING TEST =====")
        print("Resource ID:", resource.id)
        print("Extracted text length:", len(extracted_text))
        print("New chunk count:", len(test_chunks))

        for i, chunk in enumerate(test_chunks, start=1):
            print(
                f"\nChunk {i} ({len(chunk)} characters): "
                f"{chunk[:200]!r}"
            )

        # 11. Create and save the chunks and embeddings once.
        chunk_count = create_document_chunks(
            text=extracted_text,
            resource_id=resource.id,
            db=db,
        )

        # 12. Commit the resource and chunks together.
        db.commit()

        return {
            "message": (
                "Document uploaded, text extracted, "
                "and chunks created successfully."
            ),
            "resource_id": resource.id,
            "filename": resource.original_filename,
            "mime_type": resource.mime_type,
            "extraction_status": resource.extraction_status,
            "extracted_characters": len(extracted_text),
            "chunks_created": chunk_count,
        }

    except HTTPException:
        # Preserve intentional responses such as 400, 409, and 413.
        db.rollback()
        raise

    except IntegrityError as exc:
        # A concurrent upload may pass the initial duplicate check,
        # but the database constraint prevents both from being saved.
        db.rollback()

        if stored_path is not None:
            stored_path.unlink(missing_ok=True)

        existing_document = (
            db.query(Resource)
            .filter(
                Resource.user_id == current_user.id,
                Resource.file_hash == locals().get("file_hash"),
                Resource.resource_type == "document",
            )
            .first()
        )

        if existing_document:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "This document has already been uploaded.",
                    "existing_resource_id": existing_document.id,
                    "filename": existing_document.original_filename,
                },
            ) from exc

        raise HTTPException(
            status_code=500,
            detail="A database error occurred while saving the document.",
        ) from exc

    except ValueError as exc:
        db.rollback()

        if stored_path is not None:
            stored_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        db.rollback()

        if stored_path is not None:
            stored_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail="Document upload failed. Please try again.",
        ) from exc

    finally:
        await file.close()