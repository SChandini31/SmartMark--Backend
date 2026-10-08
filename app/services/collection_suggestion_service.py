import re
from sqlalchemy.orm import Session

from app.models.collection import Collection
from app.models.resource import Resource


STOP_WORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in",
    "for", "on", "with", "is", "are", "this", "that",
    "guide", "tutorial", "complete", "introduction"
}


def extract_keywords(text: str) -> set[str]:
    if not text:
        return set()

    words = re.findall(r"[a-zA-Z0-9]+", text.lower())

    return {
        word
        for word in words
        if len(word) > 2 and word not in STOP_WORDS
    }


def suggest_collections(
    resource: Resource,
    user_id: int,
    db: Session,
    limit: int = 3
):
    collections = (
        db.query(Collection)
        .filter(Collection.user_id == user_id)
        .all()
    )

    if not collections:
        return []

    resource_text = f"{resource.title or ''} {resource.description or ''}"
    resource_keywords = extract_keywords(resource_text)

    if not resource_keywords:
        return []

    suggestions = []

    for collection in collections:
        collection_text = (
            f"{collection.name or ''} "
            f"{collection.description or ''}"
        )

        collection_keywords = extract_keywords(collection_text)

        if not collection_keywords:
            continue

        matched_keywords = resource_keywords & collection_keywords

        if not matched_keywords:
            continue

        score = len(matched_keywords) / len(resource_keywords)

        suggestions.append({
            "collection_id": collection.id,
            "collection_name": collection.name,
            "score": round(score, 2),
            "matched_keywords": sorted(matched_keywords)
        })

    suggestions.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return suggestions[:limit]