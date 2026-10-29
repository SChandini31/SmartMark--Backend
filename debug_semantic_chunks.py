from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.document_chunk import DocumentChunk
from app.models.resource import Resource
from app.services.embedding_service import generate_embedding


def main():
    query = "microcontroller programming"
    resource_id = 62

    query_embedding = generate_embedding(query)

    with SessionLocal() as db:
        distance = DocumentChunk.embedding.cosine_distance(
            query_embedding
        )

        rows = (
            db.query(
                DocumentChunk.id,
                DocumentChunk.chunk_index,
                DocumentChunk.content,
                distance.label("distance"),
            )
            .join(
                Resource,
                Resource.id == DocumentChunk.resource_id,
            )
            .filter(
                Resource.id == resource_id,
                DocumentChunk.embedding.is_not(None),
            )
            .order_by(distance)
            .all()
        )

        if not rows:
            print(f"No embedded chunks found for resource {resource_id}.")
            return

        print(f"Query: {query}")
        print(f"Resource ID: {resource_id}")
        print(f"Stored chunks: {len(rows)}")

        for row in rows:
            print("\n" + "=" * 70)
            print(f"Chunk ID: {row.id}")
            print(f"Chunk index: {row.chunk_index}")
            print(f"Cosine distance: {float(row.distance):.4f}")
            print(f"Similarity: {1 - float(row.distance):.4f}")
            print(f"Content:\n{row.content[:1000]}")


if __name__ == "__main__":
    main()