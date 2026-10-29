from typing import Optional

from pydantic import BaseModel, ConfigDict, HttpUrl,  Field

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
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    resource_type: Optional[str] = None
    source_domain: Optional[str] = None
    preview_image: Optional[str] = None
    collection_id: Optional[int] = None

    # Uploaded document metadata
    original_filename: Optional[str] = None
    mime_type: Optional[str] = None
    extraction_status: Optional[str] = None
    extracted_text: Optional[str] = None
    
    created_at: Optional[object] = None
    updated_at: Optional[object] = None
    last_accessed_at: Optional[object] = None
    is_favorite: bool = False


# ============================================================
# RESOURCE CREATE RESPONSE
# ============================================================

class ResourceCreateResponse(BaseModel):
    resource: ResourceResponse
    keywords: list[str]
    suggested_tags: list[TagSuggestion]


class CodeSnippetCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    code: str = Field(min_length=1)
    language: str = Field(min_length=1, max_length=50)
    description: Optional[str] = None
    collection_id: Optional[int] = None


class BulkResourceDelete(BaseModel):
    resource_ids: list[int] = Field(min_length=1, max_length=100)

class BulkCollectionSuggestionRequest(BaseModel):
    resource_ids: list[int] = Field(min_length=2, max_length=100)