from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.core.dependencies import get_current_user
from app.schemas.resource import ResourceResponse
from app.services.semantic_search_service import semantic_search


router = APIRouter(
    prefix="/api/search",
    tags=["Semantic Search"]
)


@router.get(
    "/semantic",
    response_model=list[ResourceResponse]
)
def semantic_search_endpoint(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    resources = semantic_search(
        query_text=q,
        user_id=current_user.id,
        db=db,
        limit=limit
    )

    return resources