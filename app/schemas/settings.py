from pydantic import BaseModel, EmailStr
from datetime import datetime


class ProfileResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    created_at: datetime
    rediscovery_emails_enabled: bool

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    name: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


class PreferencesResponse(BaseModel):
    rediscovery_emails_enabled: bool


class PreferencesUpdate(BaseModel):
    rediscovery_emails_enabled: bool