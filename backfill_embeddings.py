# scripts/backfill_embeddings.py
from app.db.database import SessionLocal
from app.models.resource import Resource
from app.models.document_chunk import DocumentChunk
from app.services.embedding_service import generate_embedding


def main():
    db = SessionLocal()

    # 1. Resource-level embeddings: title + description + start of text.
    resources = db.query(Resource).filter(Resource.embedding.is_(None)).all()
    for r in resources:
        parts = [r.title, r.description, (r.extracted_text or "")[:1000]]
        text = "\n".join(p for p in parts if p).strip()
        if len(text) < 10:
            continue
        r.embedding = generate_embedding(text)
    db.commit()

    # 2. Re-embed every chunk with its title prepended.
    rows = (
        db.query(DocumentChunk, Resource)
        .join(Resource, Resource.id == DocumentChunk.resource_id)
        .filter(DocumentChunk.content.is_not(None))
        .all()
    )
    for chunk, resource in rows:
        chunk.embedding = generate_embedding(
            f"{resource.title or ''}\n{chunk.content}"
        )
    db.commit()
    db.close()


if __name__ == "__main__":
    main()