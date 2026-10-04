import hashlib
from datetime import datetime, timezone

from app.models.password_reset_token import PasswordResetToken
from app.schemas.auth import ResetPasswordRequest

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.services.email_service import send_email
from app.services.password_reset_service import create_password_reset_token
from app.services.email_service import send_email

from app.db.database import get_db
from app.models.user import User
from app.schemas.auth import RegisterRequest, UserResponse
from app.core.security import hash_password
from app.core.dependencies import get_current_user
from app.schemas.auth import (
    RegisterRequest,
    UserResponse,
    LoginRequest,
    TokenResponse,
)

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
)


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"]
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register_user(
    user_data: RegisterRequest,
    db: Session = Depends(get_db)
):
    # Normalize email
    email = user_data.email.lower().strip()

    # Check for duplicate email
    existing_user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered"
        )

    # Hash password
    hashed_password = hash_password(user_data.password)

    # Create user
    new_user = User(
        name=user_data.name.strip(),
        email=email,
        password_hash=hashed_password
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    send_email(
    to_email=new_user.email,
    subject="Welcome to SmartMark!",
    body=f"""Hi {new_user.name},

Welcome to SmartMark!

Your account has been successfully created.

SmartMark helps you save, organize, search, and rediscover your useful digital resources.

Happy organizing!

— SmartMark Team
"""
)

    return new_user


@router.post("/forgot-password")
def forgot_password(
    email: str,
    db: Session = Depends(get_db)
):
    email = email.lower().strip()

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    # Don't reveal whether an email exists
    if not user:
        return {
            "message": "If the email is registered, a password reset link has been sent."
        }

    # Generate reset token
    raw_token = create_password_reset_token(
        user_id=user.id,
        db=db
    )

    # Temporary frontend URL
    reset_link = (
        f"http://localhost:5173/reset-password?token={raw_token}"
    )

    send_email(
        to_email=user.email,
        subject="Reset your SmartMark password",
        body=f"""Hi {user.name},

We received a request to reset your SmartMark password.

Click the link below to reset your password:

{reset_link}

This link will expire in 30 minutes.

If you did not request a password reset, you can safely ignore this email.

— SmartMark Team
"""
    )

    return {
        "message": "If the email is registered, a password reset link has been sent."
    }


@router.post("/login", response_model=TokenResponse)
def login_user(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    email = login_data.email.lower().strip()

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not verify_password(
        login_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    access_token = create_access_token(user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user)
):
    return current_user

@router.post("/reset-password")
def reset_password(
    reset_data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    token_hash = hashlib.sha256(
        reset_data.token.encode()
    ).hexdigest()

    reset_token = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == token_hash
        )
        .first()
    )

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    if reset_token.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has already been used"
        )

    if reset_token.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    user = (
        db.query(User)
        .filter(User.id == reset_token.user_id)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found"
        )

    user.password_hash = hash_password(
        reset_data.new_password
    )

    reset_token.used_at = datetime.now(timezone.utc)

    db.commit()

    return {
        "message": "Password has been reset successfully"
    }