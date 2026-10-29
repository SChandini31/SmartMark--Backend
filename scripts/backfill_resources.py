
import asyncio
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.resource import Resource
from app.models.document_chunk import DocumentChunk

from app.services.document_extraction_service import extract_text_from_file
from app.services.document_chunk_service import create_document_chunks
from app.services.webpage_extraction_service import extract_webpage_text
from app.services.github_service import extract_github_readme
from app.services.youtube_service import extract_video_transcript


# SAFETY SETTINGS
DRY_RUN = False
USER_ID = 5  # Test with user 5 first. Use None only after verification.

UPLOAD_ROOT = Path("uploads/documents").resolve()


def get_chunk_count(db: Session, resource_id: int) -> int:
    return (
        db.query(DocumentChunk)
        .filter(DocumentChunk.resource_id == resource_id)
        .count()
    )


def resolve_file_path(file_path: str) -> Path:
    path = Path(file_path)

    if not path.is_absolute():
        path = Path.cwd() / path

    return path.resolve()


async def extract_url_content(resource: Resource):
    """Extract content using the existing service for each URL type."""
    if not resource.url:
        raise ValueError("Resource has no URL.")

    hostname = (urlparse(resource.url).hostname or "").lower()

    if hostname in {"github.com", "www.github.com"}:
        result = await extract_github_readme(resource.url)
        return (
            result.get("extracted_text"),
            result.get("extraction_status") or "completed",
        )

    if hostname in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
    }:
        result = extract_video_transcript(resource.url)

        if isinstance(result, dict):
            return (
                result.get("extracted_text"),
                result.get("extraction_status") or "completed",
            )

        raise ValueError("Unexpected response from YouTube transcript extractor.")

    text = await extract_webpage_text(resource.url)
    return text, "completed"


def needs_repair(resource: Resource, chunk_count: int) -> bool:
    status = (resource.extraction_status or "").lower()
    kind = (resource.resource_type or "").lower()

    if status == "pending":
        return bool(resource.url or resource.file_path)

    if status == "completed" and resource.extracted_text:
        if chunk_count == 0 and kind != "image":
            return True

    return False


async def process_resource(db: Session, resource_id: int) -> None:
    resource = (
        db.query(Resource)
        .filter(Resource.id == resource_id)
        .first()
    )

    if resource is None:
        print(f"[SKIP] {resource_id}: resource no longer exists")
        return

    original_status = resource.extraction_status
    old_text = resource.extracted_text or ""
    old_chunks = get_chunk_count(db, resource.id)

    try:
        text = old_text.strip()
        new_status = "completed"

        if resource.file_path:
            path = resolve_file_path(resource.file_path)

            # Ensure the file is inside the intended upload directory.
            if not path.is_relative_to(UPLOAD_ROOT):
                raise ValueError(
                    f"Stored file path is outside upload directory: {path}"
                )

            if not path.is_file():
                raise FileNotFoundError(
                    f"Stored file not found: {path}"
                )

            # Re-extract pending files and completed files missing chunks.
            if original_status == "pending" or old_chunks == 0:
                text = extract_text_from_file(str(path)).strip()

        elif resource.url:
            text, new_status = await extract_url_content(resource)
            text = (text or "").strip()

        else:
            print(f"[SKIP] {resource.id}: no URL or stored file path")
            return

        # Handle resources that legitimately have no transcript.
        if new_status == "metadata_only" and not text:
            if DRY_RUN:
                db.rollback()
                print(
                    f"[DRY RUN] {resource.id}: transcript unavailable; "
                    "would retain metadata_only status."
                )
            else:
                resource.extracted_text = None
                resource.extraction_status = "metadata_only"
                db.commit()
                print(
                    f"[OK] {resource.id}: transcript unavailable; "
                    "metadata retained."
                )
            return

        if not text:
            raise ValueError("Extraction returned no readable text.")

        # Generate chunks and embeddings using the existing service.
        resource.extracted_text = text

        count = create_document_chunks(
            text=text,
            resource_id=resource.id,
            db=db,
        )

        if count == 0:
            raise ValueError("No chunks were generated.")

        resource.extraction_status = "completed"

        if DRY_RUN:
            db.rollback()
            print(
                f"[DRY RUN] {resource.id}: extraction succeeded; "
                f"{len(text)} text characters; {count} chunks generated. "
                "Database changes rolled back."
            )
        else:
            db.commit()
            print(
                f"[OK] {resource.id}: saved "
                f"{len(text)} text characters and {count} chunks."
            )

    except Exception as exc:
        db.rollback()
        print(
            f"[FAILED] {resource_id}: "
            f"{type(exc).__name__}: {exc}"
        )

        # Only mark pending resources failed during a real run.
        if original_status == "pending" and not DRY_RUN:
            failed_resource = (
                db.query(Resource)
                .filter(Resource.id == resource_id)
                .first()
            )

            if failed_resource:
                failed_resource.extraction_status = "failed"
                db.commit()


async def main():
    db = SessionLocal()

    try:
        resources = (
            db.query(Resource)
            .order_by(Resource.id.asc())
            .all()
        )

        if USER_ID is not None:
            resources = [
                resource
                for resource in resources
                if resource.user_id == USER_ID
            ]

        candidates = []

        for resource in resources:
            chunk_count = get_chunk_count(db, resource.id)

            if needs_repair(resource, chunk_count):
                candidates.append(resource.id)
                print(
                    f"[CANDIDATE] id={resource.id} "
                    f"title={resource.title!r} "
                    f"status={resource.extraction_status!r} "
                    f"text_length={len(resource.extracted_text or '')} "
                    f"chunks={chunk_count}"
                )

        print(f"\nFound {len(candidates)} candidate resources.")
        print(f"DRY_RUN={DRY_RUN}")

        for resource_id in candidates:
            await process_resource(db, resource_id)

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
