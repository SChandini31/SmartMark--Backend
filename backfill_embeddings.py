from app.db.database import SessionLocal
from app.models.resource import Resource
from app.models.collection import Collection
from app.services.embedding_service import generate_embedding


db = SessionLocal()

try:
    resources = (
        db.query(Resource)
        .filter(Resource.embedding.is_(None))
        .all()
    )

    print(f"Found {len(resources)} resources without embeddings.")

    for resource in resources:

        embedding_text = " ".join(
            filter(
                None,
                [
                    resource.title,
                    resource.description,
                    resource.source_domain
                ]
            )
        )

        if not embedding_text.strip():
            print(
                f"Skipping Resource {resource.id}: "
                "no text available"
            )
            continue

        resource.embedding = generate_embedding(
            embedding_text
        )

        print(
            f"Generated embedding for Resource "
            f"{resource.id}: {resource.title}"
        )

    db.commit()

    print("\nEmbedding backfill completed successfully!")

finally:
    db.close()