
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.resource import Resource
from app.models.user import User


router = APIRouter(
    prefix="/api/resources",
    tags=["Resource Files"],
)

# Resolve paths relative to the backend project directory.
BACKEND_ROOT = Path(__file__).resolve().parents[2]

ALLOWED_UPLOAD_DIRS = {
    (BACKEND_ROOT / "uploads" / "documents").resolve(),
    (BACKEND_ROOT / "uploads" / "images").resolve(),
}


@router.get("/{resource_id}/file")
def open_resource_file(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. Find a resource belonging to the logged-in user.
    resource = (
        db.query(Resource)
        .filter(
            Resource.id == resource_id,
            Resource.user_id == current_user.id,
        )
        .first()
    )

    if not resource:
        raise HTTPException(
            status_code=404,
            detail="Resource not found.",
        )

    # 2. Check that this resource is an uploaded file.
    if resource.resource_type not in {"document", "image"}:
        raise HTTPException(
            status_code=400,
            detail="This resource is not an uploaded document or image.",
        )

    if not resource.file_path:
        raise HTTPException(
            status_code=404,
            detail="No uploaded file is associated with this resource.",
        )

    # 3. Resolve the stored path and restrict access to upload folders.
    try:
        file_path = Path(resource.file_path).resolve()
        file_path.relative_to(next(
            directory
            for directory in ALLOWED_UPLOAD_DIRS
            if file_path.is_relative_to(directory)
        ))
    except (ValueError, StopIteration, OSError):
        raise HTTPException(
            status_code=404,
            detail="The stored file path is invalid.",
        )

    # 4. Confirm that the file exists.
    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="The uploaded file could not be found on the server.",
        )

    # 5. Return the file for inline browser viewing.
    filename = resource.original_filename or file_path.name
    media_type = resource.mime_type or "application/octet-stream"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )
