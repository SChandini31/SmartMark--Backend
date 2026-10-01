from pydantic import BaseModel
from typing import Optional
from pydantic import BaseModel


class TagCreate(BaseModel):
    name: str

class TagSuggestion(BaseModel):
    id: int
    name: str

class TagUpdate(BaseModel):
    name: Optional[str] = None

class TagSuggestionResponse(BaseModel):
    resource_id: int
    keywords: list[str]
    suggested_tags: list[TagSuggestion]
    
class TagResponse(BaseModel):
    id: int
    user_id: int
    name: str

    class Config:
        from_attributes = True