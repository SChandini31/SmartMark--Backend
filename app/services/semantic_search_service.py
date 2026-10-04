from sqlalchemy.orm import Session

from app.models.resource import Resource
from app.services.embedding_service import generate_embedding


def semantic_search(
    query_text: str,
    user_id: int,
    db: Session,
    limit: int = 10
):
    """
    Search the user's resources using semantic similarity.
    """

    if not query_text or not query_text.strip():
        raise ValueError("Search query cannot be empty")

    # Generate embedding for the user's search query
    query_embedding = generate_embedding(query_text)

    # Calculate cosine distance between the query
    # and each resource embedding.
    distance = Resource.embedding.cosine_distance(
        query_embedding
    )

    resources = (
        db.query(Resource)
        .filter(
            Resource.user_id == user_id,
            Resource.embedding.is_not(None)
        )
        .order_by(distance)
        .limit(limit)
        .all()
    )

    return resources