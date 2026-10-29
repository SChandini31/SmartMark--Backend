from sqlalchemy.orm import Session

from app.models.resource import Resource
from app.models.document_chunk import DocumentChunk
from app.services.embedding_service import generate_embedding


# Lowered from 0.70. Tune on real queries (0.60 - 0.65 is a good range
# for all-MiniLM-L6-v2). Lower = stricter.
MAX_COSINE_DISTANCE = 0.65


def semantic_search(
    query_text: str,
    user_id: int,
    db: Session,
    limit: int = 10,
):
    """
    Return unique resources ranked by their best cosine distance.

    Each result is (resource, cosine_distance).
    Lower distance means a closer embedding match.
    """

    if not query_text or not query_text.strip():
        raise ValueError("Search query cannot be empty")

    if limit < 1:
        raise ValueError("Limit must be greater than zero")

    query_embedding = generate_embedding(query_text.strip())
    best_matches = {}
    candidate_limit = min(limit * 5, 200)

    # Search contextual document-chunk embeddings.
    chunk_distance = DocumentChunk.embedding.cosine_distance(query_embedding)

    chunk_results = (
        db.query(DocumentChunk, Resource, chunk_distance)
        .join(Resource, Resource.id == DocumentChunk.resource_id)
        .filter(
            Resource.user_id == user_id,
            DocumentChunk.embedding.is_not(None),
            chunk_distance <= MAX_COSINE_DISTANCE,
        )
        .order_by(chunk_distance)
        .limit(candidate_limit)
        .all()
    )

    for chunk, resource, distance in chunk_results:
        distance = float(distance)
        previous = best_matches.get(resource.id)

        if previous is None or distance < previous[1]:
            best_matches[resource.id] = (resource, distance)

    # Also search resource-level embeddings.
    resource_distance = Resource.embedding.cosine_distance(query_embedding)

    resource_results = (
        db.query(Resource, resource_distance)
        .filter(
            Resource.user_id == user_id,
            Resource.embedding.is_not(None),
            resource_distance <= MAX_COSINE_DISTANCE,
        )
        .order_by(resource_distance)
        .limit(candidate_limit)
        .all()
    )

    for resource, distance in resource_results:
        distance = float(distance)
        previous = best_matches.get(resource.id)

        if previous is None or distance < previous[1]:
            best_matches[resource.id] = (resource, distance)

    ranked_matches = sorted(best_matches.values(), key=lambda item: item[1])

    return ranked_matches[:limit]


def semantic_search_with_passages(
    query_text: str,
    user_id: int,
    db: Session,
    limit: int = 10,
):
    """
    Return unique resources with their best matching document chunk.

    Each result is (resource, cosine_distance, matching_chunk).
    Lower distance means a closer embedding match.
    """
    if not query_text or not query_text.strip():
        raise ValueError("Search query cannot be empty")

    if limit < 1:
        raise ValueError("Limit must be greater than zero")

    query_embedding = generate_embedding(query_text.strip())
    best_matches = {}
    candidate_limit = min(limit * 5, 200)

    # Search document chunks and retain the actual best-matching chunk.
    chunk_distance = DocumentChunk.embedding.cosine_distance(query_embedding)

    chunk_results = (
        db.query(DocumentChunk, Resource, chunk_distance)
        .join(Resource, Resource.id == DocumentChunk.resource_id)
        .filter(
            Resource.user_id == user_id,
            DocumentChunk.embedding.is_not(None),
            chunk_distance <= MAX_COSINE_DISTANCE,
        )
        .order_by(chunk_distance)
        .limit(candidate_limit)
        .all()
    )

    for chunk, resource, distance in chunk_results:
        distance = float(distance)
        previous = best_matches.get(resource.id)

        if previous is None or distance < previous[1]:
            best_matches[resource.id] = (resource, distance, chunk)

    # Search resource-level embeddings too.
    resource_distance = Resource.embedding.cosine_distance(query_embedding)

    resource_results = (
        db.query(Resource, resource_distance)
        .filter(
            Resource.user_id == user_id,
            Resource.embedding.is_not(None),
            resource_distance <= MAX_COSINE_DISTANCE,
        )
        .order_by(resource_distance)
        .limit(candidate_limit)
        .all()
    )

    for resource, distance in resource_results:
        distance = float(distance)

        # Add the resource-level match only when no chunk match exists.
        # If a chunk already matched, preserve its passage and score together.
        if resource.id not in best_matches:
            best_matches[resource.id] = (
                resource,
                distance,
                None,
            )
    ranked_matches = sorted(best_matches.values(), key=lambda item: item[1])

    return ranked_matches[:limit]