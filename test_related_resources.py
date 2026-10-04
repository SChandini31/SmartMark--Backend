from app.db.database import SessionLocal
from app.services.related_resources_service import find_related_resources


db = SessionLocal()

try:
    results = find_related_resources(
        resource_id=9,
        user_id=3,
        db=db,
        limit=5
    )

    print("Related Resources:")
    print("------------------")

    if results is None:
        print("Resource not found")

    elif not results:
        print("No related resources found")

    else:
        for resource in results:
            print(
                f"ID: {resource.id} | "
                f"Title: {resource.title}"
            )

finally:
    db.close()