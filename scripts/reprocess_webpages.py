
import asyncio

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.resource import Resource
from app.services.webpage_extraction_service import extract_webpage_text
from app.services.document_chunk_service import create_document_chunks


RESOURCE_IDS = [13, 26, 30]

# Avoid replacing existing content with a tiny homepage teaser or listing.
MIN_TEXT_LENGTH = 500


async def main():
    db: Session = SessionLocal()

    try:
        resources = (
            db.query(Resource)
            .filter(
                Resource.id.in_(RESOURCE_IDS),
                Resource.user_id == 5,
            )
            .order_by(Resource.id)
            .all()
        )

        found_ids = {resource.id for resource in resources}
        missing_ids = set(RESOURCE_IDS) - found_ids

        if missing_ids:
            print(f"Resources not found for user 5: {sorted(missing_ids)}")

        if not resources:
            print("No matching resources found.")
            return

        for resource in resources:
            print(f"\nProcessing resource {resource.id}: {resource.title}")
            print(f"URL: {resource.url}")

            try:
                new_text = await extract_webpage_text(resource.url)

                print(f"Extracted characters: {len(new_text)}")

                if len(new_text) < MIN_TEXT_LENGTH:
                    print(
                        "SKIPPED: Extracted text is too short. "
                        "Existing content and chunks will be preserved."
                    )
                    db.rollback()
                    continue

                old_text = resource.extracted_text
                old_status = resource.extraction_status

                try:
                    resource.extracted_text = new_text
                    resource.extraction_status = "completed"

                    chunk_count = create_document_chunks(
                        text=new_text,
                        resource_id=resource.id,
                        db=db,
                    )

                    if chunk_count == 0:
                        raise ValueError(
                            "No chunks were generated; refusing to save."
                        )

                    db.commit()

                    print("SUCCESS")
                    print(f"Saved characters: {len(new_text)}")
                    print(f"New chunks: {chunk_count}")
                    print("Resource embedding and chunk embeddings regenerated.")

                except Exception:
                    db.rollback()
                    print(
                        "FAILED: Database update rolled back; "
                        "the previous saved data should remain intact."
                    )
                    raise

            except Exception as exc:
                db.rollback()
                print(f"ERROR: {type(exc).__name__}: {exc}")
                print("Moving to the next resource.")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
