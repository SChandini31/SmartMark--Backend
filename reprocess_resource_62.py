import app.models
from app.db.database import SessionLocal
from app.models.resource import Resource
from app.models.document_chunk import DocumentChunk
from app.services.document_chunk_service import create_document_chunks

RESOURCE_ID = 62

db = SessionLocal()

try:
    resource = (
        db.query(Resource)
        .filter(Resource.id == RESOURCE_ID)
        .first()
    )

    if resource is None:
        raise ValueError(f"Resource {RESOURCE_ID} not found")

    if not resource.extracted_text or not resource.extracted_text.strip():
        raise ValueError("Resource has no extracted text; nothing changed.")

    print("Resource:", resource.title)
    print("Extracted characters:", len(resource.extracted_text))

    old_count = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.resource_id == RESOURCE_ID)
        .count()
    )
    print("Existing chunks:", old_count)

    new_count = create_document_chunks(
        text=resource.extracted_text,
        resource_id=RESOURCE_ID,
        db=db,
    )

    db.commit()

    saved_count = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.resource_id == RESOURCE_ID)
        .count()
    )

    print("New chunks generated:", new_count)
    print("Chunks saved:", saved_count)
    print("Reprocessing completed successfully.")

except Exception:
    db.rollback()
    raise

finally:
    db.close()
