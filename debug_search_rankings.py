
import app.models

from app.db.database import SessionLocal
from app.services.semantic_search_service import semantic_search

USER_ID = 5
QUERIES = [
    "microcontroller programming",
    "Arduino",
    "Arduino Uno R3",
]

db = SessionLocal()

try:
    for query in QUERIES:
        print(f"\n{'=' * 65}")
        print(f"QUERY: {query}")

        results = semantic_search(
            query_text=query,
            user_id=USER_ID,
            db=db,
            limit=10,
        )

        if not results:
            print("No results returned.")
            continue

        for rank, (resource, distance) in enumerate(results, start=1):
            print(
                f"{rank}. {resource.title}"
                f" | ID={resource.id}"
                f" | distance={float(distance):.4f}"
                f" | score={1 - float(distance):.4f}"
            )

finally:
    db.close()
