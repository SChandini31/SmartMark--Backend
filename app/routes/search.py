from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.db.database import get_db
from app.models.user import User
from app.models.resource import Resource
from app.models.tag import Tag
from app.models.collection import Collection
from app.models.resource_tag import ResourceTag
from app.core.dependencies import get_current_user
from app.schemas.resource import ResourceResponse


router = APIRouter(
    prefix="/api/search",
    tags=["Search"]
)


@router.get("/", response_model=list[ResourceResponse])
def search_resources(
    q: str = Query(..., min_length=1),
    resource_type: str | None = None,
    collection_id: int | None = None,
    sort_by: str = "newest",
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # --------------------------------------------------
    # Validate collection ownership
    # --------------------------------------------------

    if collection_id is not None:
        collection = (
            db.query(Collection)
            .filter(
                Collection.id == collection_id,
                Collection.user_id == current_user.id
            )
            .first()
        )

        if collection is None:
            raise HTTPException(
                status_code=404,
                detail="Collection not found"
            )

    # --------------------------------------------------
    # Search term
    # --------------------------------------------------

    search_term = f"%{q.lower()}%"

    # --------------------------------------------------
    # Base search query
    # --------------------------------------------------

    query = (
        db.query(Resource)
        .outerjoin(
            ResourceTag,
            ResourceTag.resource_id == Resource.id
        )
        .outerjoin(
            Tag,
            Tag.id == ResourceTag.tag_id
        )
        .filter(
            Resource.user_id == current_user.id,
            or_(
                Resource.title.ilike(search_term),
                Resource.description.ilike(search_term),
                Resource.url.ilike(search_term),
                Resource.source_domain.ilike(search_term),
                Tag.name.ilike(search_term)
            )
        )
    )

    # --------------------------------------------------
    # Resource type filter
    # --------------------------------------------------

    if resource_type is not None:
        query = query.filter(
            Resource.resource_type == resource_type
        )

    # --------------------------------------------------
    # Collection filter
    # --------------------------------------------------

    if collection_id is not None:
        query = query.filter(
            Resource.collection_id == collection_id
        )

    # --------------------------------------------------
    # Sorting
    # --------------------------------------------------

    if sort_by == "newest":
        query = query.order_by(
            Resource.created_at.desc()
        )

    elif sort_by == "oldest":
        query = query.order_by(
            Resource.created_at.asc()
        )

    elif sort_by == "title":
        query = query.order_by(
            Resource.title.asc()
        )

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid sort_by. Use newest, oldest, or title."
        )

    # --------------------------------------------------
    # Pagination
    # --------------------------------------------------

    offset = (page - 1) * limit

    resources = (
        query
        .distinct()
        .offset(offset)
        .limit(limit)
        .all()
    )

    return resources