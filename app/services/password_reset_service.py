import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.password_reset_token import PasswordResetToken


RESET_TOKEN_EXPIRE_MINUTES = 30


def create_password_reset_token(
    user_id: int,
    db: Session
):
    # Generate a secure random token
    raw_token = secrets.token_urlsafe(32)

    # Hash the token before storing it
    token_hash = hashlib.sha256(
        raw_token.encode()
    ).hexdigest()

    # Set expiration time
    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    )

    # Store hashed token
    reset_token = PasswordResetToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at
    )

    db.add(reset_token)
    db.commit()

    return raw_token