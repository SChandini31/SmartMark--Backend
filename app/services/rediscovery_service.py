from datetime import datetime, timedelta, timezone
from app.services.email_service import send_email
from sqlalchemy.orm import Session

from app.models.resource import Resource


def get_rediscovery_resources(
    user_id: int,
    db: Session,
    days: int = 30,
    limit: int = 10
):
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    resources = (
        db.query(Resource)
        .filter(
            Resource.user_id == user_id,

            # Resource must be at least `days` old
            Resource.created_at <= cutoff_date,

            # Never accessed OR not accessed for `days`
            (
                (Resource.last_accessed_at.is_(None)) |
                (Resource.last_accessed_at <= cutoff_date)
            )
        )
        .order_by(
            Resource.last_accessed_at.asc().nullsfirst(),
            Resource.created_at.asc()
        )
        .limit(limit)
        .all()
    )

    return resources

def send_rediscovery_email(
    user_email: str,
    user_name: str,
    resources
):
    if not resources:
        return

    resource_lines = []

    for resource in resources:
        title = resource.title or resource.url
        resource_lines.append(f"• {title}")

    resource_list = "\n".join(resource_lines)

    subject = "Rediscover your SmartMark resources"

    body = f"""Hi {user_name},

You have some resources in SmartMark that you haven't visited recently.

{resource_list}

Take a look and rediscover something useful!

— SmartMark Team
"""

    send_email(
        to_email=user_email,
        subject=subject,
        body=body
    )