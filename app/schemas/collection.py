from pydantic import BaseModel
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
    description: Optional[str]

    class Config:
        from_attributes = True

class CollectionSuggestion(BaseModel):
    collection_id: int
    collection_name: str
    score: float
    matched_keywords: list[str]