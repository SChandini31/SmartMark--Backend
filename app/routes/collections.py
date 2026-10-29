from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.models.user import User
from app.models.collection import Collection
from app.schemas.collection import (
    CollectionCreate,
    CollectionUpdate,
    CollectionResponse,
    BulkResourceAssignment,
)
from app.core.dependencies import get_current_user
from app.models.resource import Resource
from app.schemas.resource import ResourceResponse

router = APIRouter(
    prefix="/api/collections",
    tags=["Collections"]
)


# CREATE COLLECTION
@router.post("/", response_model=CollectionResponse)
def create_collection(
    collection_data: CollectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    collection = Collection(
        user_id=current_user.id,
        name=collection_data.name,
        description=collection_data.description
    )

    db.add(collection)
    db.commit()
    db.refresh(collection)

    return collection


# GET ALL MY COLLECTIONS
@router.get("/", response_model=list[CollectionResponse])
def get_collections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    collections = (
        db.query(
            Collection,
            func.count(Resource.id).label("resource_count")
        )
        .outerjoin(
            Resource,
            Resource.collection_id == Collection.id
        )
        .filter(
            Collection.user_id == current_user.id
        )
        .group_by(Collection.id)
        .order_by(Collection.created_at.desc())
        .all()
    )

    return [
        {
            "id": collection.id,
            "user_id": collection.user_id,
            "name": collection.name,
            "description": collection.description,
            "resource_count": resource_count
        }
        for collection, resource_count in collections
    ]


# GET ONE COLLECTION
@router.get("/{collection_id}", response_model=CollectionResponse)
def get_collection(
    collection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
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

    return collection


# UPDATE COLLECTION
@router.put("/{collection_id}", response_model=CollectionResponse)
def update_collection(
    collection_id: int,
    collection_data: CollectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
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

    update_data = collection_data.model_dump(
        exclude_unset=True
    )

    if "name" in update_data:
        collection.name = update_data["name"]

    if "description" in update_data:
        collection.description = update_data["description"]

    db.commit()
    db.refresh(collection)

    return collection


# DELETE COLLECTION
@router.delete("/{collection_id}")
def delete_collection(
    collection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
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

    db.delete(collection)
    db.commit()

    return {
        "message": "Collection deleted successfully"
    }

@router.get(
    "/{collection_id}/resources",
    response_model=list[ResourceResponse]
)
def get_collection_resources(
    collection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
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

    resources = (
        db.query(Resource)
        .filter(
            Resource.collection_id == collection_id,
            Resource.user_id == current_user.id
        )
        .order_by(Resource.created_at.desc())
        .all()
    )

    return resources


# BULK ADD / MOVE RESOURCES TO A COLLECTION
@router.post("/{collection_id}/resources/bulk")
def bulk_assign_resources(
    collection_id: int,
    assignment_data: BulkResourceAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. Verify that the collection belongs to the logged-in user.
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

    # 2. Remove duplicate IDs while preserving their order.
    resource_ids = list(dict.fromkeys(assignment_data.resource_ids))

    # 3. Fetch only resources owned by the logged-in user.
    resources = (
        db.query(Resource)
        .filter(
            Resource.id.in_(resource_ids),
            Resource.user_id == current_user.id,
        )
        .all()
    )

    # 4. Reject the entire request if any resource is missing
    # or belongs to another user.
    found_ids = {resource.id for resource in resources}
    missing_ids = sorted(set(resource_ids) - found_ids)

    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Some resources were not found or are inaccessible.",
                "resource_ids": missing_ids,
            },
        )

    # 5. Assign all selected resources to the collection.
    try:
        for resource in resources:
            resource.collection_id = collection.id

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "message": "Resources added to collection successfully.",
        "collection_id": collection.id,
        "collection_name": collection.name,
        "assigned_count": len(resources),
        "resource_ids": resource_ids,
    }
