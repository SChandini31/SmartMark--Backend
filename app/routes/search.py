from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pydantic import BaseModel
from typing import Optional
import re

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


class SearchResult(BaseModel):
    resource: ResourceResponse
    matched_in: list[str]
    snippet: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]


@router.get("/", response_model=SearchResponse)
def search_resources(
    q: str = Query(..., min_length=1, max_length=200),
    resource_type: str | None = None,
    collection_id: int | None = None,
    sort_by: str = "newest",
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query_text = q.strip()

    if not query_text:
        raise HTTPException(
            status_code=422,
            detail="Search keyword cannot be empty or whitespace.",
        )

    normalized_q = "".join(query_text.casefold().split())

    # Whole-word matching is used for relevance ranking.
    whole_word_query = (
        query_text
        if re.fullmatch(r"[A-Za-z0-9]+", query_text)
        else None
    )

    # Validate the collection belongs to the current user.
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

    # IMPORTANT:
    # Normal search uses metadata only.
    # Do not include Resource.extracted_text here.
    searchable_fields = [
        Resource.title,
        Resource.description,
        Resource.url,
        Resource.source_domain,
        Resource.original_filename,
        Tag.name,
    ]

    normalized_fields = [
        func.lower(
            func.replace(
                func.coalesce(field, ""),
                " ",
                "",
            )
        )
        for field in searchable_fields
    ]

    # Find resources belonging to this user whose metadata
    # contains the search query.
    query = (
        db.query(Resource)
        .outerjoin(
            ResourceTag,
            ResourceTag.resource_id == Resource.id,
        )
        .outerjoin(
            Tag,
            Tag.id == ResourceTag.tag_id,
        )
        .filter(
            Resource.user_id == current_user.id,
            or_(*[
                field.like(f"%{normalized_q}%")
                for field in normalized_fields
            ]),
        )
    )

    if resource_type is not None:
        query = query.filter(
            Resource.resource_type == resource_type
        )

    if collection_id is not None:
        query = query.filter(
            Resource.collection_id == collection_id
        )

    # Validate sorting.
    if sort_by not in {"newest", "oldest", "title"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid sort_by. Use newest, oldest, or title.",
        )

    # Count unique matching resources before pagination.
    total = query.order_by(None).distinct().count()

    # Fetch candidates before ranking and pagination.
    resources = query.order_by(None).distinct().all()

    def normalize(value: str | None) -> str:
        return "".join((value or "").casefold().split())

    def has_whole_word(value: str | None) -> bool:
        if not whole_word_query or not value:
            return False

        pattern = (
            r"(?<![A-Za-z0-9])"
            + re.escape(whole_word_query)
            + r"(?![A-Za-z0-9])"
        )

        return re.search(
            pattern,
            value,
            flags=re.IGNORECASE,
        ) is not None

    def relevance_rank(resource: Resource) -> int:
        title = resource.title or ""

        metadata_values = [
            resource.description,
            resource.url,
            resource.source_domain,
            resource.original_filename,
        ]

        # Priority 1: Exact title match.
        if normalize(title) == normalized_q:
            return 0

        # Priority 2: Title starts with the query.
        if normalize(title).startswith(normalized_q):
            return 1

        # Priority 3: Whole-word match in title.
        if has_whole_word(title):
            return 2

        # Priority 4: Partial match in title.
        if normalized_q in normalize(title):
            return 3

        # Priority 5: Whole-word match in other metadata.
        if any(
            has_whole_word(value)
            for value in metadata_values
        ):
            return 4

        # Priority 6: Partial match in other metadata.
        if any(
            normalized_q in normalize(value)
            for value in metadata_values
        ):
            return 5

        # Priority 7: Match in a tag.
        # Tag matches are included in SQL filtering.
        return 6

    def secondary_sort_key(resource: Resource):
        if sort_by == "oldest":
            return (
                resource.created_at.timestamp()
                if resource.created_at
                else float("inf")
            )

        if sort_by == "title":
            return (resource.title or "").casefold()

        # Newest first; resources without a date go last.
        return -(
            resource.created_at.timestamp()
            if resource.created_at
            else 0
        )

    # Rank first, then apply the selected secondary sort.
    resources.sort(
        key=lambda resource: (
            relevance_rank(resource),
            secondary_sort_key(resource),
        )
    )

    # Apply pagination after relevance ranking.
    start = (page - 1) * limit
    resources = resources[start:start + limit]

    results = []

    for resource in resources:
        matched_in = []

        metadata_fields = {
            "title": resource.title,
            "description": resource.description,
            "filename": resource.original_filename,
            "url": resource.url,
            "source_domain": resource.source_domain,
        }

        # Identify which metadata fields actually matched.
        for field_name, value in metadata_fields.items():
            if value and normalized_q in normalize(value):
                matched_in.append(field_name)

        # If no metadata field matched, the query matched a tag.
        if not matched_in:
            matched_in.append("tag")

        # Create a useful preview from matching metadata.
        snippet = (
            resource.description
            or resource.title
            or resource.original_filename
            or resource.url
        )

        if snippet and len(snippet) > 240:
            snippet = snippet[:237].rstrip() + "..."

        resource_data = ResourceResponse.model_validate(
            resource,
            from_attributes=True,
        ).model_dump(exclude={"extracted_text"})

        results.append({
            "resource": resource_data,
            "matched_in": matched_in,
            "snippet": snippet,
        })

    return {
        "query": query_text,
        "total": total,
        "results": results,
    }