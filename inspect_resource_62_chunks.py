
from app.db.database import SessionLocal
from app.models.document_chunk import DocumentChunk

db = SessionLocal()

try:
    chunk_ids = [596, 589, 583, 587, 588]

    chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.resource_id == 62,
            DocumentChunk.id.in_(chunk_ids),
        )
        .order_by(DocumentChunk.id)
        .all()
    )

    for chunk in chunks:
        print(f"\n{'=' * 60}")
        print(f"Chunk ID: {chunk.id}")
        print(f"Has embedding: {chunk.embedding is not None}")
        print("Stored content:")
        print(chunk.content)

finally:
    db.close()
