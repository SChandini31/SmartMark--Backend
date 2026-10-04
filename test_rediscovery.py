from app.db.database import SessionLocal
from app.services.rediscovery_service import get_rediscovery_resources


db = SessionLocal()

try:
    results = get_rediscovery_resources(
        user_id=3,
        db=db,
        days=30,
        limit=10
    )

    print("Rediscovery Resources:")
    print("----------------------")

    if not results:
        print("No rediscovery resources found.")

    else:
        for resource in results:
            print(
                f"ID: {resource.id} | "
                f"Title: {resource.title} | "
                f"Created: {resource.created_at} | "
                f"Last Accessed: {resource.last_accessed_at}"
            )

finally:
    db.close()