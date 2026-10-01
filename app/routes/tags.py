from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.models.tag import Tag
from app.schemas.tag import (
    TagCreate,
    TagUpdate,
    TagResponse
)
from app.core.dependencies import get_current_user
from app.models.resource import Resource
from app.models.resource_tag import ResourceTag
from app.schemas.resource import ResourceResponse


router = APIRouter(
    prefix="/api/tags",
    tags=["Tags"]
)


# ============================================================
# CREATE TAG
# ============================================================

@router.post("/", response_model=TagResponse)
def create_tag(
    tag_data: TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check if this user already has a tag with the same name
    existing_tag = (
        db.query(Tag)
        .filter(
            Tag.user_id == current_user.id,
            Tag.name == tag_data.name
        )
        .first()
    )

    if existing_tag:
        raise HTTPException(
            status_code=400,
            detail="Tag already exists"
        )

    tag = Tag(
        user_id=current_user.id,
        name=tag_data.name
    )

    db.add(tag)
    db.commit()
    db.refresh(tag)

    return tag


# ============================================================
# GET ALL MY TAGS
# ============================================================

@router.get("/", response_model=list[TagResponse])
def get_tags(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    tags = (
        db.query(Tag)
        .filter(
            Tag.user_id == current_user.id
        )
        .order_by(Tag.name.asc())
        .all()
    )

    return tags


# ============================================================
# GET ONE TAG
# ============================================================

@router.get("/{tag_id}", response_model=TagResponse)
def get_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    tag = (
        db.query(Tag)
        .filter(
            Tag.id == tag_id,
            Tag.user_id == current_user.id
        )
        .first()
    )

    if tag is None:
        raise HTTPException(
            status_code=404,
            detail="Tag not found"
        )

    return tag


# ============================================================
# UPDATE TAG
# ============================================================

@router.put("/{tag_id}", response_model=TagResponse)
def update_tag(
    tag_id: int,
    tag_data: TagUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Find tag belonging to current user
    tag = (
        db.query(Tag)
        .filter(
            Tag.id == tag_id,
            Tag.user_id == current_user.id
        )
        .first()
    )

    if tag is None:
        raise HTTPException(
            status_code=404,
            detail="Tag not found"
        )

    # Only update fields provided
    update_data = tag_data.model_dump(
        exclude_unset=True
    )

    if "name" in update_data:

        new_name = update_data["name"]

        # Check duplicate tag name
        existing_tag = (
            db.query(Tag)
            .filter(
                Tag.user_id == current_user.id,
                Tag.name == new_name,
                Tag.id != tag_id
            )
            .first()
        )

        if existing_tag:
            raise HTTPException(
                status_code=400,
                detail="Tag already exists"
            )

        tag.name = new_name

    db.commit()
    db.refresh(tag)

    return tag


# ============================================================
# DELETE TAG
# ============================================================

@router.delete("/{tag_id}")
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Find tag belonging to current user
    tag = (
        db.query(Tag)
        .filter(
            Tag.id == tag_id,
            Tag.user_id == current_user.id
        )
        .first()
    )

    if tag is None:
        raise HTTPException(
            status_code=404,
            detail="Tag not found"
        )

    db.delete(tag)
    db.commit()

    return {
        "message": "Tag deleted successfully"
    }

# ============================================================
# GET RESOURCES BY TAG
# ============================================================

@router.get(
    "/{tag_id}/resources",
    response_model=list[ResourceResponse]
)
def get_tag_resources(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check tag ownership
    tag = (
        db.query(Tag)
        .filter(
            Tag.id == tag_id,
            Tag.user_id == current_user.id
        )
        .first()
    )

    if tag is None:
        raise HTTPException(
            status_code=404,
            detail="Tag not found"
        )

    resources = (
        db.query(Resource)
        .join(
            ResourceTag,
            ResourceTag.resource_id == Resource.id
        )
        .filter(
            ResourceTag.tag_id == tag_id,
            Resource.user_id == current_user.id
        )
        .order_by(Resource.created_at.desc())
        .all()
    )

    return resources