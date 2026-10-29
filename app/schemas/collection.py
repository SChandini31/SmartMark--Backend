from pydantic import BaseModel, Field
from typing import Optional


class CollectionCreate(BaseModel):
    name: str
    description: Optional[str] = None


class CollectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class CollectionResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: Optional[str] = None
    resource_count: int = 0

    class Config:
        from_attributes = True


class CollectionSuggestion(BaseModel):
    collection_id: int
    collection_name: str
    score: float
    matched_keywords: list[str]


class CollectionRecommendation(BaseModel):
    suggested_collections: list[CollectionSuggestion]
    recommend_new_collection: bool
    suggested_collection_name: Optional[str] = None
    message: str

class BulkResourceAssignment(BaseModel):
    resource_ids: list[int] = Field(min_length=1, max_length=100)