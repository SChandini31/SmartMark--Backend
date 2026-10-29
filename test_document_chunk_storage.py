from app.db.database import SessionLocal
from app.models.resource import Resource
from app.models.document_chunk import DocumentChunk
from app.services.document_chunk_service import create_document_chunks

RESOURCE_ID = 36

db = SessionLocal()

try:
    resource = (
        db.query(Resource)
        .filter(Resource.id == RESOURCE_ID)
        .first()
    )

    if not resource:
        raise ValueError(f"Resource {RESOURCE_ID} was not found")

    if not resource.extracted_text:
        raise ValueError("The resource has no extracted text")

    existing_chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.resource_id == RESOURCE_ID)
        .count()
    )

    if existing_chunks:
        print(f"Test stopped: resource already has {existing_chunks} chunks.")
    else:
        count = create_document_chunks(
            text=resource.extracted_text,
            resource_id=resource.id,
            db=db,
        )

        db.commit()
        print(f"Chunks stored successfully: {count}")

        saved_chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.resource_id == RESOURCE_ID)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )

        print(f"Verified database records: {len(saved_chunks)}")
        print(
            "First chunk embedding dimensions:",
            len(saved_chunks[0].embedding)
            if saved_chunks and saved_chunks[0].embedding
            else 0,
        )

except Exception:
    db.rollback()
    raise

finally:
    db.close()
