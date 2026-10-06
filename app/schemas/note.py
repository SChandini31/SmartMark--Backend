from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class NoteCreate(BaseModel):
    title: Optional[str] = None
    content: str
    resource_id: Optional[int] = None


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    resource_id: Optional[int] = None


class NoteResponse(BaseModel):
    id: int
    user_id: int
    resource_id: Optional[int]
    title: Optional[str]
    content: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True