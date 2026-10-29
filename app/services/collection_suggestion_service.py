import re
from sqlalchemy.orm import Session

from app.models.collection import Collection
from app.models.resource import Resource


STOP_WORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in",
    "for", "on", "with", "is", "are", "this", "that",
    "guide", "tutorial", "complete", "introduction",
    "from", "by", "as", "at", "be", "it", "its",
    "into", "your", "you", "how", "what", "when",
    "where", "why", "which", "using", "use", "about",
    "course", "courses", "learning", "learn", "professional",
    "certificate", "certificates", "provided", "provides",
    "free", "online", "program", "programs", "module",
    "modules", "training", "beginner", "beginners"
}


def extract_keywords(text: str) -> set[str]:
    if not text:
        return set()

    words = re.findall(r"[a-zA-Z0-9+#.]+", text.lower())

    keywords = set()

    for word in words:
        word = word.strip(".")
        if len(word) > 2 and word not in STOP_WORDS:
            keywords.add(word)

    return keywords


def suggest_collection_name(title: str) -> str | None:
    if not title:
        return None

    # Remove file extensions.
    name = re.sub(
        r"\.(pdf|docx?|txt|pptx?|xlsx?|csv|md)$",
        "",
        title.strip(),
        flags=re.IGNORECASE
    )

    # Remove dates.
    name = re.sub(
        r"\b\d{1,4}[._/-]\d{1,2}[._/-]\d{2,4}\b",
        "",
        name
    )

    # Replace separators with spaces.
    name = re.sub(r"[_-]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" ._-")

    # Remove generic words, not specific subject names.
    generic_words = {
        "course", "courses", "tutorial", "tutorials",
        "guide", "guides", "complete", "introduction",
        "beginner", "beginners", "learning", "learn",
        "certificate", "certificates", "professional",
        "online", "free", "training", "program",
        "programs", "notes", "document", "documents",
        "resources", "resource", "overview", "basics",
        "explained", "ebook", "study", "material"
    }

    words = [
        word for word in name.split()
        if word.casefold() not in generic_words
    ]

    if not words:
        return None

    # Build the collection name from the remaining title words.
    name = " ".join(words).strip()

    # Avoid creating a suggestion with no meaningful keywords.
    if not extract_keywords(name):
        return None

    return name[:100].title()

def suggest_collections(
    resource: Resource,
    user_id: int,
    db: Session,
    limit: int = 3
) -> dict:
    collections = (
        db.query(Collection)
        .filter(Collection.user_id == user_id)
        .all()
    )

    # Give title and description priority.
    primary_text = " ".join([
        resource.title or "",
        resource.description or ""
    ])

    primary_keywords = extract_keywords(primary_text)

    # Use extracted content only as supporting evidence.
    content_keywords = extract_keywords(resource.extracted_text or "")

    suggestions = []

    for collection in collections:
        collection_text = " ".join([
            collection.name or "",
            collection.description or ""
        ])

        collection_keywords = extract_keywords(collection_text)

        if not collection_keywords:
            continue

        primary_matches = primary_keywords & collection_keywords
        content_matches = content_keywords & collection_keywords

        # A match must have evidence in the title/description,
        # or at least two supporting content keywords.
        if not primary_matches and len(content_matches) < 2:
            continue

        # Title and description matches carry more weight.
        weighted_matches = (
            len(primary_matches) * 3
            + len(content_matches - primary_matches)
        )

        coverage = weighted_matches / (
            len(collection_keywords) * 3
        )

        score = min(coverage, 1.0)

        # Avoid weak matches based on incidental extracted content.
        if primary_matches and score < 0.15:
            continue

        if not primary_matches and score < 0.30:
            continue

        matched_keywords = sorted(
            primary_matches | content_matches
        )

        suggestions.append({
            "collection_id": collection.id,
            "collection_name": collection.name,
            "score": round(score, 2),
            "matched_keywords": matched_keywords
        })

    suggestions.sort(
        key=lambda item: (
            item["score"],
            len(item["matched_keywords"])
        ),
        reverse=True
    )

    suggestions = suggestions[:max(0, limit)]

    recommend_new = len(suggestions) == 0
    suggested_name = (
        suggest_collection_name(resource.title)
        if recommend_new
        else None
    )

    if suggestions:
        message = "Found existing collections that may fit this resource."
    elif collections:
        message = (
            "No suitable existing collection found. "
            "Consider creating a new collection."
        )
    else:
        message = (
            "You don't have any collections yet. "
            "Consider creating your first collection."
        )

    return {
        "suggested_collections": suggestions,
        "recommend_new_collection": recommend_new,
        "suggested_collection_name": suggested_name,
        "message": message
    }

def suggest_collections_for_resources(
    resources: list[Resource],
    user_id: int,
    db: Session,
    limit: int = 3,
) -> dict:
    if not resources:
        return {
            "suggested_collections": [],
            "recommend_new_collection": True,
            "suggested_collection_name": None,
            "message": "Select resources to get collection suggestions.",
        }

    # Aggregate each collection's score across the selection.
    collection_scores = {}

    for resource in resources:
        result = suggest_collections(
            resource=resource,
            user_id=user_id,
            db=db,
            limit=1000,
        )

        for suggestion in result["suggested_collections"]:
            collection_id = suggestion["collection_id"]

            if collection_id not in collection_scores:
                collection_scores[collection_id] = {
                    "collection_id": collection_id,
                    "collection_name": suggestion["collection_name"],
                    "total_score": 0.0,
                    "matched_keywords": set(),
                    "resource_matches": 0,
                }

            item = collection_scores[collection_id]
            item["total_score"] += suggestion["score"]
            item["matched_keywords"].update(
                suggestion["matched_keywords"]
            )
            item["resource_matches"] += 1

    # Average each collection's score across ALL selected resources.
    # A collection that matches only one resource should not
    # automatically outrank a collection that fits the whole selection.
    suggestions = []

    for item in collection_scores.values():
        score = item["total_score"] / len(resources)

        suggestions.append({
            "collection_id": item["collection_id"],
            "collection_name": item["collection_name"],
            "score": round(score, 2),
            "matched_keywords": sorted(item["matched_keywords"]),
        })

    suggestions.sort(
        key=lambda item: (
            item["score"],
            len(item["matched_keywords"]),
        ),
        reverse=True,
    )

    suggestions = [
        item for item in suggestions
        if item["score"] > 0
    ][:max(0, limit)]

    if suggestions:
        message = (
            f"Recommendations generated for {len(resources)} selected resources."
        )
    else:
        message = (
            "No suitable existing collection found. "
            "Consider creating a new collection."
        )

    return {
        "suggested_collections": suggestions,
        "recommend_new_collection": len(suggestions) == 0,
        "suggested_collection_name": None,
        "message": message,
    }