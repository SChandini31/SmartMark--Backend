from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pwdlib import PasswordHash

from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.settings import (
    ProfileResponse,
    ProfileUpdate,
    PasswordChange,
    PreferencesResponse,
    PreferencesUpdate,
)

router = APIRouter(
    prefix="/api/settings",
    tags=["Settings"]
)

password_hash = PasswordHash.recommended()


# ============================================================
# GET PROFILE
# ============================================================

@router.get("/profile", response_model=ProfileResponse)
def get_profile(
    current_user: User = Depends(get_current_user)
):
    return current_user


# ============================================================
# UPDATE PROFILE
# ============================================================

@router.put("/profile", response_model=ProfileResponse)
def update_profile(
    profile_data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    current_user.name = profile_data.name

    db.commit()
    db.refresh(current_user)

    return current_user


# ============================================================
# CHANGE PASSWORD
# ============================================================

@router.put("/password")
def change_password(
    password_data: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not password_hash.verify(
        password_data.current_password,
        current_user.password_hash
    ):
        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect"
        )

    if password_data.new_password != password_data.confirm_password:
        raise HTTPException(
            status_code=400,
            detail="New passwords do not match"
        )

    current_user.password_hash = password_hash.hash(
        password_data.new_password
    )

    db.commit()

    return {
        "message": "Password changed successfully"
    }


# ============================================================
# GET PREFERENCES
# ============================================================

@router.get(
    "/preferences",
    response_model=PreferencesResponse
)
def get_preferences(
    current_user: User = Depends(get_current_user)
):
    return {
        "rediscovery_emails_enabled":
            current_user.rediscovery_emails_enabled
    }


# ============================================================
# UPDATE PREFERENCES
# ============================================================

@router.put(
    "/preferences",
    response_model=PreferencesResponse
)
def update_preferences(
    preferences_data: PreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    current_user.rediscovery_emails_enabled = (
        preferences_data.rediscovery_emails_enabled
    )

    db.commit()
    db.refresh(current_user)

    return {
        "rediscovery_emails_enabled":
            current_user.rediscovery_emails_enabled
    }