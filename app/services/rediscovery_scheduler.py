from datetime import datetime, timedelta, timezone

from app.db.database import SessionLocal
from app.models.user import User
from app.services.rediscovery_service import (
    get_rediscovery_resources,
    send_rediscovery_email
)


REDISCOVERY_DAYS = 30
EMAIL_COOLDOWN_DAYS = 30


def run_rediscovery_job():
    db = SessionLocal()

    try:
        now = datetime.now(timezone.utc)

        users = db.query(User).all()

        for user in users:

            # Don't send another email if one was sent recently
            if user.last_rediscovery_email_at is not None:
                next_allowed = (
                    user.last_rediscovery_email_at
                    + timedelta(days=EMAIL_COOLDOWN_DAYS)
                )

                if now < next_allowed:
                    continue

            resources = get_rediscovery_resources(
                user_id=user.id,
                db=db,
                days=REDISCOVERY_DAYS,
                limit=10
            )

            if not resources:
                continue

            send_rediscovery_email(
                user_email=user.email,
                user_name=user.name,
                resources=resources
            )

            user.last_rediscovery_email_at = now
            db.commit()

            print(
                f"Rediscovery email sent to {user.email}"
            )

    except Exception as e:
        db.rollback()
        print("Rediscovery job failed:", e)

    finally:
        db.close()