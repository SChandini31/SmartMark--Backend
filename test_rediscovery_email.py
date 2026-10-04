from app.db.database import SessionLocal
from app.models.user import User
from app.services.rediscovery_service import get_rediscovery_resources
from app.services.rediscovery_service import send_rediscovery_email


db = SessionLocal()

try:
    user = db.query(User).filter(User.id == 3).first()

    if not user:
        print("User not found")
    else:
        resources = get_rediscovery_resources(
            user_id=user.id,
            db=db,
            days=30,
            limit=10
        )

        print(f"Found {len(resources)} rediscovery resources")

        send_rediscovery_email(
            user_email="chandinisaravana@gmail.com",
            user_name="Chandini",
            resources=resources
        )

        print("Rediscovery email sent!")

finally:
    db.close()