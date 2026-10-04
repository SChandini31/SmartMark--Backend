from sqlalchemy.orm import Session

from app.models.resource import Resource


def find_related_resources(
    resource_id: int,
    user_id: int,
    db: Session,
    limit: int = 5
):
    # Get the current resource
    resource = (
        db.query(Resource)
        .filter(
            Resource.id == resource_id,
            Resource.user_id == user_id
        )
        .first()
    )

    if resource is None:
        return None

    # Current resource doesn't have an embedding
    if resource.embedding is None:
        return []

    # Calculate cosine distance
    distance = Resource.embedding.cosine_distance(
        resource.embedding
    )

    # Find similar resources
    related_resources = (
        db.query(Resource)
        .filter(
            Resource.user_id == user_id,
            Resource.id != resource_id,
            Resource.embedding.is_not(None)
        )
        .order_by(distance)
        .limit(limit)
        .all()
    )

    return related_resources