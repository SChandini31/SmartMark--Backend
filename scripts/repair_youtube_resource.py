import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import SessionLocal
from app.models.resource import Resource
from app.services.youtube_service import extract_video_transcript
from app.services.document_chunk_service import create_document_chunks


RESOURCE_ID = 47
EXPECTED_USER_ID = 5
EXPECTED_VIDEO_ID = "bm0OyhwFDuY"
MIN_TRANSCRIPT_LENGTH = 1000


def main():
    db = SessionLocal()

    try:
        resource = (
            db.query(Resource)
            .filter(
                Resource.id == RESOURCE_ID,
                Resource.user_id == EXPECTED_USER_ID,
            )
            .with_for_update()
            .first()
        )

        if resource is None:
            raise ValueError("Resource 46 was not found for user 5.")

        result = extract_video_transcript(resource.url)

        if result["video_id"] != EXPECTED_VIDEO_ID:
            raise ValueError("The extracted video ID does not match.")

        new_text = result["extracted_text"].strip()

        if len(new_text) < MIN_TRANSCRIPT_LENGTH:
            raise ValueError(
                f"Transcript is too short: {len(new_text)} characters."
            )

        if "About Press Copyright" in new_text[:500]:
            raise ValueError("The extracted text looks like a YouTube footer.")

        print("Verified resource:", resource.id, resource.title)
        print("New transcript length:", len(new_text))
        print("Transcript preview:", new_text[:300])

        # Keep all database changes in one transaction.
        resource.extracted_text = new_text
        resource.extraction_status = "completed"

        chunk_count = create_document_chunks(
            text=new_text,
            resource_id=resource.id,
            db=db,
        )

        if chunk_count == 0:
            raise ValueError("No chunks were generated.")

        # Verify new chunks before committing.
        db.flush()

        from app.models.document_chunk import DocumentChunk

        saved_chunk_count = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.resource_id == resource.id)
            .count()
        )

        if saved_chunk_count != chunk_count:
            raise ValueError("Saved chunk count does not match.")

        db.commit()

        print(f"\nSUCCESS — resource {RESOURCE_ID} repaired.")
        print("Saved transcript length:", len(new_text))
        print("Saved chunk count:", saved_chunk_count)

    except Exception:
        db.rollback()
        print("\nFAILED — database transaction rolled back.")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
