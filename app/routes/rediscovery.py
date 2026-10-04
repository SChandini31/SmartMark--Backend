from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.core.dependencies import get_current_user
from app.schemas.resource import ResourceResponse
from app.services.rediscovery_service import get_rediscovery_resources


router = APIRouter(
    prefix="/api/rediscovery",
    tags=["Rediscovery"]
)

@router.get(
    "/",
    response_model=list[ResourceResponse]
)
def rediscovery_resources(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return get_rediscovery_resources(
        user_id=current_user.id,
        db=db,
        days=days,
        limit=limit
    )