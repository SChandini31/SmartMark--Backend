from pydantic import BaseModel, HttpUrl
from typing import Optional

from app.schemas.tag import TagSuggestion


# ============================================================
# CREATE RESOURCE
# ============================================================

class ResourceCreate(BaseModel):
    url: HttpUrl
    title: Optional[str] = None
    description: Optional[str] = None
    resource_type: Optional[str] = None
    collection_id: Optional[int] = None


# ============================================================
# UPDATE RESOURCE
# ============================================================

class ResourceUpdate(BaseModel):
    url: Optional[HttpUrl] = None
    title: Optional[str] = None
    description: Optional[str] = None
    resource_type: Optional[str] = None
    collection_id: Optional[int] = None


# ============================================================
# RESOURCE RESPONSE
# ============================================================

class ResourceResponse(BaseModel):
    id: int
    user_id: int
    url: str
    title: Optional[str]
    description: Optional[str]
    resource_type: Optional[str]
    source_domain: Optional[str]
    preview_image: Optional[str]
    collection_id: Optional[int]

    class Config:
        from_attributes = True


# ============================================================
# RESOURCE CREATE RESPONSE
# ============================================================

class ResourceCreateResponse(BaseModel):
    resource: ResourceResponse
    keywords: list[str]
    suggested_tags: list[TagSuggestion]