from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.resource import Resource
from app.services.document_chunking_service import chunk_text
from app.services.contextual_embedding_service import build_contextual_chunks
from app.services.embedding_service import generate_embedding


MAX_EMBEDDING_CHARS = 1000


def create_document_chunks(
    text: str,
    resource_id: int,
    db: Session,
) -> int:
    normalized_text = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
    )

    chunks = chunk_text(normalized_text)

    if not chunks:
        return 0

    resource = (
        db.query(Resource)
        .filter(Resource.id == resource_id)
        .first()
    )

    if resource is None:
        raise ValueError(f"Resource {resource_id} not found")

    contextual_chunks = build_contextual_chunks(
        normalized_text,
        chunks,
        max_chars=MAX_EMBEDDING_CHARS,
    )

    # Generate all embeddings before replacing any existing chunks.
    resource_embedding = generate_embedding(normalized_text)

    records = []

    for index, item in enumerate(contextual_chunks):
        embedding_text = item["embedding_text"]

        if len(embedding_text) > MAX_EMBEDDING_CHARS:
            raise ValueError(
                f"Chunk {index} embedding text exceeds "
                f"{MAX_EMBEDDING_CHARS} characters"
            )

        embedding = generate_embedding(embedding_text)

        records.append(
            DocumentChunk(
                resource_id=resource_id,
                chunk_index=index,
                content=item["content"],
                embedding=embedding,
            )
        )

    # Replace old chunks only after embedding generation succeeds.
    (
        db.query(DocumentChunk)
        .filter(DocumentChunk.resource_id == resource_id)
        .delete(synchronize_session=False)
    )

    resource.embedding = resource_embedding
    db.add_all(records)
    db.flush()

    return len(records)
