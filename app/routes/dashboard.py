from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.dependencies import get_current_user

from app.models.user import User
from app.models.resource import Resource
from app.models.collection import Collection
from app.models.tag import Tag
from app.models.note import Note


router = APIRouter(
    prefix="/api/dashboard",
    tags=["Dashboard"],
)


@router.get("/")
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    # ---------------------------------------------------------
    # BASIC COUNTS
    # ---------------------------------------------------------

    resource_count = (
        db.query(func.count(Resource.id))
        .filter(Resource.user_id == current_user.id)
        .scalar()
    )

    collection_count = (
        db.query(func.count(Collection.id))
        .filter(Collection.user_id == current_user.id)
        .scalar()
    )

    tag_count = (
        db.query(func.count(Tag.id))
        .filter(Tag.user_id == current_user.id)
        .scalar()
    )

    note_count = (
        db.query(func.count(Note.id))
        .filter(Note.user_id == current_user.id)
        .scalar()
    )

    favorite_count = (
        db.query(func.count(Resource.id))
        .filter(
            Resource.user_id == current_user.id,
            Resource.is_favorite == True,
        )
        .scalar()
    )

    # ---------------------------------------------------------
    # FORGOTTEN RESOURCES
    # ---------------------------------------------------------

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)

    forgotten_count = (
        db.query(func.count(Resource.id))
        .filter(
            Resource.user_id == current_user.id,
            Resource.created_at <= cutoff_date,
            (
                (Resource.last_accessed_at.is_(None))
                | (Resource.last_accessed_at <= cutoff_date)
            ),
        )
        .scalar()
    )

    # ---------------------------------------------------------
    # SAVING ACTIVITY - LAST 7 DAYS
    # ---------------------------------------------------------

    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=6)

    activity_rows = (
        db.query(
            func.date(Resource.created_at).label("date"),
            func.count(Resource.id).label("count"),
        )
        .filter(
            Resource.user_id == current_user.id,
            func.date(Resource.created_at) >= start_date,
        )
        .group_by(func.date(Resource.created_at))
        .order_by(func.date(Resource.created_at))
        .all()
    )

    activity_map = {
        row.date: row.count
        for row in activity_rows
    }

    saving_activity = []

    for i in range(7):
        current_date = start_date + timedelta(days=i)

        saving_activity.append({
            "date": current_date.strftime("%a"),
            "count": activity_map.get(current_date, 0),
        })

    # ---------------------------------------------------------
    # RESOURCE TYPES
    # ---------------------------------------------------------

    resource_type_rows = (
        db.query(
            Resource.resource_type,
            func.count(Resource.id).label("count"),
        )
        .filter(
            Resource.user_id == current_user.id,
        )
        .group_by(Resource.resource_type)
        .order_by(func.count(Resource.id).desc())
        .all()
    )

    resource_types = []

    for row in resource_type_rows:
        resource_types.append({
            "type": row.resource_type or "Other",
            "count": row.count,
        })

    # ---------------------------------------------------------
    # RECENTLY SAVED
    # ---------------------------------------------------------

    recently_saved = (
        db.query(Resource)
        .filter(
            Resource.user_id == current_user.id,
        )
        .order_by(Resource.created_at.desc())
        .limit(5)
        .all()
    )

    recent_resources = []

    for resource in recently_saved:
        recent_resources.append({
            "id": resource.id,
            "title": resource.title,
            "url": resource.url,
            "resource_type": resource.resource_type,
            "source_domain": resource.source_domain,
            "preview_image": resource.preview_image,
            "created_at": resource.created_at,
            "is_favorite": resource.is_favorite,
        })

    # ---------------------------------------------------------
    # FINAL RESPONSE
    # ---------------------------------------------------------

    return {
        "stats": {
            "resources": resource_count,
            "collections": collection_count,
            "tags": tag_count,
            "notes": note_count,
            "favorites": favorite_count,
            "forgotten_resources": forgotten_count,
        },

        "saving_activity": saving_activity,

        "resource_types": resource_types,

        "recently_saved": recent_resources,
    }