from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from urllib.parse import urlparse
from sqlalchemy import or_
from app.services.github_service import extract_github_readme
from app.schemas.resource import BulkCollectionSuggestionRequest
from app.services.webpage_extraction_service import extract_webpage_text
from app.services.document_chunk_service import create_document_chunks
from app.services.youtube_service import extract_video_transcript
from app.schemas.collection import CollectionRecommendation

import httpx
from pathlib import Path
from app.db.database import get_db
from app.models.user import User
from app.models.resource import Resource
from app.models.collection import Collection
from app.models.tag import Tag
from app.models.resource_tag import ResourceTag
from datetime import datetime, timezone
from app.services.collection_suggestion_service import ( 
    suggest_collections,
    suggest_collections_for_resources,
)
from app.schemas.collection import CollectionSuggestion

from app.services.tagging_service import (
    extract_keywords,
    suggest_tags,
)

from app.schemas.resource import (
    ResourceCreate,
    ResourceUpdate,
    ResourceResponse,
    ResourceCreateResponse,
    CodeSnippetCreate,
    BulkResourceDelete,
)

from app.schemas.tag import TagResponse, TagSuggestionResponse
from app.services.embedding_service import generate_embedding
from app.core.dependencies import get_current_user
from app.services.metadata_service import extract_metadata



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

    # Check for duplicate resource
    existing_resource = (
        db.query(Resource)
        .filter(
            Resource.user_id == current_user.id,
            Resource.url == str(resource_data.url),
        )
        .first()
    )

    if existing_resource is not None:
        raise HTTPException(
            status_code=409,
            detail="Resource already exists"
        )

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
  
    # Extract URL metadata and content
    url = str(resource_data.url)

    from urllib.parse import urlparse


    hostname = (urlparse(url).hostname or "").lower()

    is_github = hostname in {"github.com", "www.github.com"}
    is_youtube = hostname in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
    }

    if is_github:
        try:
            github_data = await extract_github_readme(url)

            metadata = {
                "title": github_data["title"],
                "description": github_data["description"],
                "preview_image": None,
                "source_domain": github_data["source_domain"],
            }

            extracted_text = github_data["extracted_text"]
            extraction_status = github_data["extraction_status"]

        except ValueError as exc:
         raise HTTPException(
            status_code=400,
            detail=str(exc),
         ) from exc

        except httpx.HTTPError as exc:
         print(f"GitHub HTTP error: {type(exc).__name__}: {exc}")
         raise HTTPException(
            status_code=502,
            detail="Could not retrieve GitHub repository information.",
            ) from exc

    elif is_youtube:
        try:
            metadata = await extract_metadata(url)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

        # Extract existing captions only; never generate a transcript.
        extracted_text = None
        extraction_status = "metadata_only"

        try:
            youtube_data = extract_video_transcript(url)
            extracted_text = youtube_data["extracted_text"]
            extraction_status = youtube_data["extraction_status"]

       
        except ValueError as exc:
            if str(exc) == "The video transcript is empty.":
                extracted_text = None
                extraction_status = "metadata_only"
            else:
                raise HTTPException(
                    status_code=400,
                    detail=str(exc),
                ) from exc

        except RuntimeError as exc:
            # Captions may be unavailable or access may be restricted.
            print(f"YouTube transcript unavailable: {exc}")

        print("YouTube extracted text length:", len(extracted_text or ""))
        print("YouTube extracted text preview:", (extracted_text or "")[:200])

    
    else:
        try:
            metadata = await extract_metadata(url)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

        # Extract readable webpage content only for ordinary webpages.
        extracted_text = None
        extraction_status = "failed"

        try:
            extracted_text = await extract_webpage_text(url)
            extraction_status = "completed"
        except (ValueError, httpx.HTTPError) as exc:
            print(f"Webpage text extraction failed: {exc}")


    embedding_text = " ".join(
        filter(
            None,
            [
                resource_data.title or metadata["title"],
                resource_data.description or metadata["description"],
                metadata["source_domain"],
            ],
        )
    )
    embedding = generate_embedding(embedding_text) if embedding_text.strip() else None

    resource = Resource(
        user_id=current_user.id,
        collection_id=resource_data.collection_id,
        url=url,
        title=resource_data.title or metadata["title"],
        description=resource_data.description or metadata["description"],
        resource_type=resource_data.resource_type,
        source_domain=metadata["source_domain"],
        preview_image=metadata["preview_image"],
        embedding=embedding,
        extracted_text=extracted_text,
        extraction_status=extraction_status,
    )

    try:
        db.add(resource)
        db.flush()

        if extracted_text:
            create_document_chunks(
                text=extracted_text,
                resource_id=resource.id,
                db=db,
            )

        db.commit()
        db.refresh(resource)

    except Exception:
        db.rollback()
        raise


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
    # Generate tag suggestions
    tag_suggestions = suggest_tags(
        keywords=keywords,
        existing_tags=existing_tags,
    )

    suggested_tags = tag_suggestions["existing_tag_matches"]

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
# GET FAVORITE RESOURCES
# ============================================================

@router.get("/favorites")
def get_favorites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    favorites = (
        db.query(Resource)
        .filter(
            Resource.user_id == current_user.id,
            Resource.is_favorite == True
        )
        .order_by(Resource.created_at.desc())
        .all()
    )

    return favorites


# ============================================================
# TOGGLE RESOURCE FAVORITE
# ============================================================

@router.patch("/{resource_id}/favorite", response_model=ResourceResponse)
def toggle_resource_favorite(
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

    resource.is_favorite = not resource.is_favorite
    db.commit()
    db.refresh(resource)
    return resource

# ============================================================
# GET RECENT RESOURCES
# ============================================================

@router.get("/recent")
def get_recent_resources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    recent_resources = (
        db.query(Resource)
        .filter(
            Resource.user_id == current_user.id,
            Resource.last_accessed_at.is_not(None)
        )
        .order_by(Resource.last_accessed_at.desc())
        .limit(20)
        .all()
    )

    return recent_resources


#bulk collection suggestions
@router.post(
    "/bulk/collection-suggestions",
    response_model=CollectionRecommendation,
)
def get_bulk_collection_suggestions(
    request: BulkCollectionSuggestionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resource_ids = list(dict.fromkeys(request.resource_ids))

    resources = (
        db.query(Resource)
        .filter(
            Resource.id.in_(resource_ids),
            Resource.user_id == current_user.id,
        )
        .all()
    )

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

    return suggest_collections_for_resources(
        resources=resources,
        user_id=current_user.id,
        db=db,
    )

#============================================================
# SUGGEST COLLECTIONS FOR RESOURCE
#============================================================    
@router.get(
    "/{resource_id}/collection-suggestions",
    response_model=CollectionRecommendation
)
def get_collection_suggestions(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    resource = (
        db.query(Resource)
        .filter(
            Resource.id == resource_id,
            Resource.user_id == current_user.id
        )
        .first()
    )

    if resource is None:
        raise HTTPException(
            status_code=404,
            detail="Resource not found"
        )

    return suggest_collections(
        resource=resource,
        user_id=current_user.id,
        db=db
    )


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

    update_data = resource_data.model_dump(exclude_unset=True)

    # Validate collection ownership before changing anything.
    if "collection_id" in update_data:
        collection_id = update_data["collection_id"]

        if collection_id is not None:
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

    # Update URL only when the request explicitly supplies it.
    if "url" in update_data:
        new_url = update_data["url"]

        # A document's URL may be null; do not turn null into "None".
        resource.url = str(new_url) if new_url is not None else None

        if new_url is not None:
            resource.source_domain = urlparse(str(new_url)).netloc
        else:
            resource.source_domain = None

    if "title" in update_data:
        resource.title = update_data["title"]

    if "description" in update_data:
        resource.description = update_data["description"]

    if "resource_type" in update_data:
        resource.resource_type = update_data["resource_type"]

    # Refresh the resource-level embedding when searchable metadata changes.
    if "title" in update_data or "description" in update_data:
        embedding_text = " ".join(
            part for part in (
                resource.title,
                resource.description,
                resource.source_domain,
            )
            if part and part.strip()
        )

        if embedding_text:
            resource.embedding = generate_embedding(embedding_text)
        else:
            resource.embedding = None

    try:
        db.commit()
        db.refresh(resource)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Resource update failed.",
        ) from exc

    return resource


# ============================================================
# BULK DELETE RESOURCES
# ============================================================

@router.delete("/bulk")
def bulk_delete_resources(
    delete_data: BulkResourceDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Remove duplicate IDs while preserving their order.
    resource_ids = list(dict.fromkeys(delete_data.resource_ids))

    # Fetch only resources owned by the logged-in user.
    resources = (
        db.query(Resource)
        .filter(
            Resource.id.in_(resource_ids),
            Resource.user_id == current_user.id,
        )
        .all()
    )

    # Reject the whole request if any resource is missing
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

    # Validate stored file paths before modifying the database.
    upload_roots = [
        Path("uploads/documents").resolve(),
        Path("uploads/images").resolve(),
        Path("uploads/videos").resolve(),
        ]

    stored_paths = []

    for resource in resources:
        if not resource.file_path:
            continue

        stored_path = Path(resource.file_path).resolve()

        # Allow files only inside an approved upload directory.
        is_allowed_path = any(
            root in stored_path.parents
            for root in upload_roots
        )

        if not is_allowed_path:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Invalid stored file path for resource {resource.id}."
                ),
            )

        stored_paths.append(stored_path)
    # Delete all selected records in one transaction.
    try:
        for resource in resources:
            db.delete(resource)

        db.commit()

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Bulk resource deletion failed.",
        ) from exc

    # Delete stored files only after the database commit succeeds.
    failed_file_deletions = []

    for stored_path in stored_paths:
        if stored_path.exists():
            try:
                stored_path.unlink()
            except OSError:
                failed_file_deletions.append(str(stored_path))

    response = {
        "message": "Resources deleted successfully.",
        "deleted_count": len(resources),
        "resource_ids": resource_ids,
    }

    if failed_file_deletions:
        response["warning"] = (
            "Some database records were deleted, but some stored files "
            "could not be removed. File cleanup needs to be retried."
        )
        response["failed_file_deletions"] = len(failed_file_deletions)

    return response


# ============================================================
# DELETE RESOURCE
# ============================================================

@router.delete("/{resource_id}")
def delete_resource(
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

    # Remember the stored document path before deleting the record.
    stored_path = None

    if resource.file_path:
        stored_path = Path(resource.file_path).resolve()
        upload_root = Path("uploads/documents").resolve()

        # Only allow deletion inside SmartMark's document upload folder.
        if (
            stored_path == upload_root
            or upload_root not in stored_path.parents
        ):
            raise HTTPException(
                status_code=500,
                detail="Invalid stored document path.",
            )

    try:
        # Delete the database record first.
        # Document chunks should cascade through the foreign key.
        db.delete(resource)
        db.commit()

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Resource deletion failed.",
        ) from exc

    # Remove the physical file after the database transaction succeeds.
    # If file deletion fails, report it so cleanup can be retried.
    if stored_path is not None and stored_path.exists():
        try:
            stored_path.unlink()
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "The resource was deleted from the database, "
                    "but its stored file could not be removed."
                ),
            ) from exc

    return {
        "message": "Resource deleted successfully",
        "resource_id": resource_id,
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

    # Extract keywords for existing-tag matching
    keywords = extract_keywords(
        title=resource.title,
        description=resource.description,
    )

    # Get the current user's existing tags
    existing_tags = (
        db.query(Tag)
        .filter(Tag.user_id == current_user.id)
        .all()
    )

    # Match extracted keywords against existing tags
    tag_suggestions = suggest_tags(
        keywords=keywords,
        existing_tags=existing_tags,
    )

    # Get matching existing tags
    existing_tag_matches = tag_suggestions["existing_tag_matches"]

    # Return the response in the expected schema format
    return {
        "resource_id": resource.id,
        "resource": resource,
        "keywords": keywords,
        "suggested_tags": existing_tag_matches,
        "existing_tag_matches": existing_tag_matches,
    }

# ============================================================
# CREATE CODE SNIPPET
# ============================================================

@router.post("/snippets", response_model=ResourceResponse, status_code=201)
def create_code_snippet(
    snippet_data: CodeSnippetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate collection ownership
    if snippet_data.collection_id is not None:
        collection = (
            db.query(Collection)
            .filter(
                Collection.id == snippet_data.collection_id,
                Collection.user_id == current_user.id,
            )
            .first()
        )

        if collection is None:
            raise HTTPException(
                status_code=404,
                detail="Collection not found",
            )

    # Prepare searchable snippet content
    code = snippet_data.code.strip()

    if not code:
        raise HTTPException(
            status_code=422,
            detail="Code snippet cannot be empty.",
        )

    language = snippet_data.language.strip().lower()

    if not language:
        raise HTTPException(
            status_code=422,
            detail="Programming language cannot be empty.",
        )

    title = snippet_data.title.strip()

    if not title:
        raise HTTPException(
            status_code=422,
            detail="Snippet title cannot be empty.",
        )

    # Generate embedding from the title, language, description, and code
    embedding_text = "\n".join(
        filter(
            None,
            [
                title,
                language,
                snippet_data.description,
                code,
            ],
        )
    )

    embedding = generate_embedding(embedding_text)

    # Store the snippet using the existing Resource model
    resource = Resource(
        user_id=current_user.id,
        collection_id=snippet_data.collection_id,
        url=None,
        title=title,
        description=snippet_data.description,
        resource_type=f"code:{language}",
        source_domain=None,
        preview_image=None,
        embedding=embedding,
        extracted_text=code,
        extraction_status="completed",
    )

    try:
        db.add(resource)
        db.flush()

        create_document_chunks(
            text=code,
            resource_id=resource.id,
            db=db,
        )

        db.commit()
        db.refresh(resource)

    except Exception:
        db.rollback()
        raise

    return resource

