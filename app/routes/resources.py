from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from urllib.parse import urlparse

from app.db.database import get_db
from app.models.user import User
from app.models.resource import Resource
from app.models.collection import Collection
from app.models.tag import Tag
from app.models.resource_tag import ResourceTag
from datetime import datetime, timezone

from app.schemas.resource import (
    ResourceCreate,
    ResourceUpdate,
    ResourceResponse,
    ResourceCreateResponse,
)

from app.schemas.tag import TagResponse, TagSuggestionResponse
from app.services.embedding_service import generate_embedding
from app.core.dependencies import get_current_user
from app.services.metadata_service import extract_metadata
from app.services.tagging_service import (
    extract_keywords,
    suggest_tags,
)


router = APIRouter(
    prefix="/api/resources",
    tags=["Resources"],
)


# ============================================================
# CREATE RESOURCE
# ============================================================

@router.post("/", response_model=ResourceCreateResponse)
async def create_resource(
    resource_data: ResourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate collection ownership if collection is provided
    if resource_data.collection_id is not None:
        collection = (
            db.query(Collection)
            .filter(
                Collection.id == resource_data.collection_id,
                Collection.user_id == current_user.id,
            )
            .first()
        )

        if collection is None:
            raise HTTPException(
                status_code=404,
                detail="Collection not found",
            )

    # Extract URL metadata
    metadata = await extract_metadata(
        str(resource_data.url)
    )

    embedding_text = " ".join(
    filter(
          None,
          [
            resource_data.title or metadata["title"],
            resource_data.description or metadata["description"],
            metadata["source_domain"]
          ]
        )
    )
    embedding = generate_embedding(embedding_text)

    # Create resource
    resource = Resource(
        user_id=current_user.id,
        collection_id=resource_data.collection_id,
        url=str(resource_data.url),
        title=(
            resource_data.title
            or metadata["title"]
        ),
        description=(
            resource_data.description
            or metadata["description"]
        ),
        resource_type=resource_data.resource_type,
        source_domain=metadata["source_domain"],
        preview_image=metadata["preview_image"],
        embedding=embedding
    )

    db.add(resource)
    db.commit()
    db.refresh(resource)

    # Extract keywords
    keywords = extract_keywords(
        title=resource.title,
        description=resource.description,
    )

    # Get user's existing tags
    existing_tags = (
        db.query(Tag)
        .filter(
            Tag.user_id == current_user.id
        )
        .all()
    )

    # Generate tag suggestions
    suggested_tags = suggest_tags(
        keywords=keywords,
        existing_tags=existing_tags,
    )

    return {
        "resource": resource,
        "keywords": keywords,
        "suggested_tags": suggested_tags,
    }


# ============================================================
# GET ALL MY RESOURCES
# ============================================================

@router.get("/", response_model=list[ResourceResponse])
def get_resources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resources = (
        db.query(Resource)
        .filter(
            Resource.user_id == current_user.id
        )
        .order_by(
            Resource.created_at.desc()
        )
        .all()
    )

    return resources


# ============================================================
# GET ONE RESOURCE
# ============================================================

@router.get("/{resource_id}", response_model=ResourceResponse)
def get_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resource = (
        db.query(Resource)
        .filter(
            Resource.id == resource_id,
            Resource.user_id == current_user.id,
        )
        .first()
    )

    if resource is None:
        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )
    resource.last_accessed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(resource)
    return resource


# ============================================================
# UPDATE RESOURCE
# ============================================================

@router.put("/{resource_id}", response_model=ResourceResponse)
def update_resource(
    resource_id: int,
    resource_data: ResourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Find resource belonging to current user
    resource = (
        db.query(Resource)
        .filter(
            Resource.id == resource_id,
            Resource.user_id == current_user.id,
        )
        .first()
    )

    if resource is None:
        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    # Get only fields provided by the user
    update_data = resource_data.model_dump(
        exclude_unset=True
    )

    # Update URL
    if "url" in update_data:
        new_url = str(update_data["url"])
        resource.url = new_url

        parsed_url = urlparse(new_url)
        resource.source_domain = parsed_url.netloc

    # Update title
    if "title" in update_data:
        resource.title = update_data["title"]

    # Update description
    if "description" in update_data:
        resource.description = update_data["description"]

    # Update resource type
    if "resource_type" in update_data:
        resource.resource_type = update_data["resource_type"]

    # Update collection
    if "collection_id" in update_data:
        collection_id = update_data["collection_id"]

        # Allow removing resource from collection
        if collection_id is None:
            resource.collection_id = None

        else:
            collection = (
                db.query(Collection)
                .filter(
                    Collection.id == collection_id,
                    Collection.user_id == current_user.id,
                )
                .first()
            )

            if collection is None:
                raise HTTPException(
                    status_code=404,
                    detail="Collection not found",
                )

            resource.collection_id = collection_id

    # Save changes
    db.commit()
    db.refresh(resource)

    return resource


# ============================================================
# DELETE RESOURCE
# ============================================================

@router.delete("/{resource_id}")
def delete_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Find resource belonging to current user
    resource = (
        db.query(Resource)
        .filter(
            Resource.id == resource_id,
            Resource.user_id == current_user.id,
        )
        .first()
    )

    if resource is None:
        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    # Delete resource
    db.delete(resource)
    db.commit()

    return {
        "message": "Resource deleted successfully"
    }


# ============================================================
# ADD TAG TO RESOURCE
# ============================================================

@router.post(
    "/{resource_id}/tags/{tag_id}",
    response_model=TagResponse,
)
def add_tag_to_resource(
    resource_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check resource ownership
    resource = (
        db.query(Resource)
        .filter(
            Resource.id == resource_id,
            Resource.user_id == current_user.id,
        )
        .first()
    )

    if resource is None:
        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    # Check tag ownership
    tag = (
        db.query(Tag)
        .filter(
            Tag.id == tag_id,
            Tag.user_id == current_user.id,
        )
        .first()
    )

    if tag is None:
        raise HTTPException(
            status_code=404,
            detail="Tag not found",
        )

    # Check whether relationship already exists
    existing_relation = (
        db.query(ResourceTag)
        .filter(
            ResourceTag.resource_id == resource_id,
            ResourceTag.tag_id == tag_id,
        )
        .first()
    )

    if existing_relation:
        raise HTTPException(
            status_code=400,
            detail="Tag already assigned to this resource",
        )

    resource_tag = ResourceTag(
        resource_id=resource_id,
        tag_id=tag_id,
    )

    db.add(resource_tag)
    db.commit()

    return tag


# ============================================================
# GET TAGS OF RESOURCE
# ============================================================

@router.get(
    "/{resource_id}/tags",
    response_model=list[TagResponse],
)
def get_resource_tags(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check resource ownership
    resource = (
        db.query(Resource)
        .filter(
            Resource.id == resource_id,
            Resource.user_id == current_user.id,
        )
        .first()
    )

    if resource is None:
        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    tags = (
        db.query(Tag)
        .join(
            ResourceTag,
            ResourceTag.tag_id == Tag.id,
        )
        .filter(
            ResourceTag.resource_id == resource_id,
            Tag.user_id == current_user.id,
        )
        .order_by(Tag.name.asc())
        .all()
    )

    return tags


# ============================================================
# REMOVE TAG FROM RESOURCE
# ============================================================

@router.delete(
    "/{resource_id}/tags/{tag_id}"
)
def remove_tag_from_resource(
    resource_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check resource ownership
    resource = (
        db.query(Resource)
        .filter(
            Resource.id == resource_id,
            Resource.user_id == current_user.id,
        )
        .first()
    )

    if resource is None:
        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    # Check tag ownership
    tag = (
        db.query(Tag)
        .filter(
            Tag.id == tag_id,
            Tag.user_id == current_user.id,
        )
        .first()
    )

    if tag is None:
        raise HTTPException(
            status_code=404,
            detail="Tag not found",
        )

    # Find relationship
    resource_tag = (
        db.query(ResourceTag)
        .filter(
            ResourceTag.resource_id == resource_id,
            ResourceTag.tag_id == tag_id,
        )
        .first()
    )

    if resource_tag is None:
        raise HTTPException(
            status_code=404,
            detail="Tag is not assigned to this resource",
        )

    db.delete(resource_tag)
    db.commit()

    return {
        "message": "Tag removed from resource successfully"
    }


# ============================================================
# SUGGEST TAGS FOR RESOURCE
# ============================================================

@router.post(
    "/{resource_id}/suggest-tags",
    response_model=TagSuggestionResponse,
)
def suggest_resource_tags(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get resource belonging to current user
    resource = (
        db.query(Resource)
        .filter(
            Resource.id == resource_id,
            Resource.user_id == current_user.id,
        )
        .first()
    )

    if resource is None:
        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    # Extract keywords from resource
    keywords = extract_keywords(
        title=resource.title,
        description=resource.description,
    )

    # Get user's existing tags
    existing_tags = (
        db.query(Tag)
        .filter(
            Tag.user_id == current_user.id
        )
        .all()
    )

    # Find matching tags
    suggested_tags = suggest_tags(
        keywords=keywords,
        existing_tags=existing_tags,
    )

    # Return suggestions
    return {
        "resource_id": resource.id,
        "keywords": keywords,
        "suggested_tags": suggested_tags,
    }
