from app.db.database import SessionLocal
from app.services.semantic_search_service import semantic_search


db = SessionLocal()

try:
    results = semantic_search(
        query_text="Python framework for building APIs",
        user_id=3,
        db=db,
        limit=5
    )

    print("Semantic Search Results:")
    print("------------------------")

    for resource in results:
        print(
            f"ID: {resource.id} | "
            f"Title: {resource.title}"
        )

finally:
    db.close()