from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.core.dependencies import get_current_user
from app.schemas.resource import ResourceResponse
from app.services.related_resources_service import find_related_resources


router = APIRouter(
    prefix="/api/resources",
    tags=["Related Resources"]
)


@router.get(
    "/{resource_id}/related",
    response_model=list[ResourceResponse]
)
def get_related_resources(
    resource_id: int,
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    resources = find_related_resources(
        resource_id=resource_id,
        user_id=current_user.id,
        db=db,
        limit=limit
    )

    if resources is None:
        raise HTTPException(
            status_code=404,
            detail="Resource not found"
        )

    return resources