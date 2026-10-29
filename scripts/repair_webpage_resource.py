import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent)
)
import asyncio

from app.db.database import SessionLocal
from app.models.resource import Resource
from app.services.webpage_extraction_service import extract_webpage_text
from app.services.document_chunk_service import create_document_chunks


RESOURCE_ID = 29


async def main():
    db = SessionLocal()

    try:
        resource = (
            db.query(Resource)
            .filter(Resource.id == RESOURCE_ID)
            .first()
        )

        if resource is None:
            raise ValueError(f"Resource {RESOURCE_ID} not found")

        if not resource.url:
            raise ValueError("This resource has no webpage URL")

        print("Resource:", resource.id, resource.title)
        print("URL:", resource.url)

        new_text = await extract_webpage_text(resource.url)

        print("\nNew extracted text length:", len(new_text))
        print("Text preview:\n", new_text[:500])

        if len(new_text.strip()) < 1000:
            raise ValueError(
                "Extracted text is unexpectedly short; refusing to update."
            )

        if new_text.lstrip().startswith(
            ("Courses", "Tutorials", "Practice Jobs")
        ):
            raise ValueError(
                "Navigation text still appears at the start; refusing update."
            )

        # Keep the original database state until all embeddings succeed.
        old_text = resource.extracted_text
        old_embedding = resource.embedding

        try:
            resource.extracted_text = new_text
            resource.extraction_status = "completed"

            chunk_count = create_document_chunks(
                text=new_text,
                resource_id=RESOURCE_ID,
                db=db,
            )

            if chunk_count == 0:
                raise ValueError("No chunks were generated")

            db.commit()

        except Exception:
            db.rollback()
            raise

        print("\nSUCCESS")
        print("Resource ID:", RESOURCE_ID)
        print("Updated text length:", len(new_text))
        print("Chunks created:", chunk_count)

    except Exception as exc:
        db.rollback()
        print("\nRepair failed:", type(exc).__name__, str(exc))
        raise

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
