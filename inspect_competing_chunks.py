
import app.models

from app.db.database import SessionLocal
from app.models.resource import Resource
from app.models.document_chunk import DocumentChunk
from app.services.embedding_service import generate_embedding

QUERIES = [
    "microcontroller programming",
    "Arduino Uno R3",
]
RESOURCE_IDS = [48, 59, 62]

db = SessionLocal()

try:
    for query in QUERIES:
        print(f"\n{'=' * 70}\nQUERY: {query}")
        query_embedding = generate_embedding(query)

        distance_expr = DocumentChunk.embedding.cosine_distance(
            query_embedding
        )

        rows = (
            db.query(
                Resource.id,
                Resource.title,
                DocumentChunk.chunk_index,
                DocumentChunk.content,
                distance_expr.label("distance"),
            )
            .join(
                DocumentChunk,
                DocumentChunk.resource_id == Resource.id,
            )
            .filter(
                Resource.id.in_(RESOURCE_IDS),
                DocumentChunk.embedding.is_not(None),
            )
            .order_by(distance_expr)
            .limit(12)
            .all()
        )

        for row in rows:
            print(
                f"\nResource {row.id}: {row.title}"
                f"\nChunk index: {row.chunk_index}"
                f"\nDistance: {float(row.distance):.4f}"
                f"\nContent: {row.content[:700]}"
            )
finally:
    db.close()
