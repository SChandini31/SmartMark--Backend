import logging
import re
from typing import Callable, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.resource import Resource

logger = logging.getLogger(__name__)

# An embedding function takes text and returns a vector (list of floats).
# Pass YOUR existing embedding function so vectors stay consistent.
EmbedFn = Callable[[str], Sequence[float]]

# --- Matching rules --------------------------------------------------------
# A candidate is accepted if EITHER:
#   * distance <= STRICT_DISTANCE                      (embedding alone), or
#   * distance <= LOOSE_DISTANCE AND it shares at least one keyword
#     with the selected resource                        (embedding + text).
# This stops weak "everything is tech/PDF" matches (no shared words) while
# still catching real matches whose embeddings are a bit noisy.
STRICT_DISTANCE = 0.22
LOOSE_DISTANCE = 0.40

# After the rules above, keep only results within this gap of the best one.
RELATIVE_MARGIN = 0.08

# Fetch more candidates than `limit`, because the rules above discard some.
CANDIDATE_MULTIPLIER = 4

# Max characters of extracted_text used when building embedding input.
EMBED_TEXT_CHARS = 1000

# Generic words that should not count as a "shared keyword".
STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "using", "how", "what",
    "tutorial", "tutorials", "guide", "complete", "introduction", "intro",
    "course", "courses", "learn", "learning", "sheet", "website", "video",
    "full", "beginners", "beginner", "free", "best", "top", "online",
    "unit", "pdf", "png", "jpg", "jpeg", "docx", "pptx", "txt", "saved",
    "resource",
}

URL_RE = re.compile(r"https?://\S+|www\.\S+")


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
def _clean_text(text: Optional[str]) -> str:
    """Remove URLs and collapse whitespace (scraped pages are full of both)."""
    text = URL_RE.sub(" ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _keywords(text: Optional[str]) -> List[str]:
    words = re.findall(r"[a-zA-Z0-9+#]{3,}", _clean_text(text).lower())
    seen, result = set(), []
    for w in words:
        if w not in STOPWORDS and w not in seen:
            seen.add(w)
            result.append(w)
    return result


def _compact(text: Optional[str]) -> str:
    """Lowercase letters/digits only, so 'Cyber Security' == 'CyberSecurity'."""
    return re.sub(r"[^a-z0-9]", "", _clean_text(text).lower())


def _keyword_score(a: Resource, b: Resource) -> int:
    """How many meaningful keywords the two resources share (0 = none)."""
    a_title = a.title or ""
    b_title = b.title or ""
    b_all = f"{b_title} {b.description or ''}"

    a_terms = set(_keywords(a_title))
    b_title_terms = set(_keywords(b_title))
    b_terms = set(_keywords(b_all))

    a_compact = _compact(a_title)
    b_compact = _compact(b_all)

    # Exact word matches.
    score = len(a_terms & b_terms)
    # Space-insensitive matches for longer words (cybersecurity / cyber security).
    score += sum(1 for t in a_terms - b_terms if len(t) >= 6 and t in b_compact)
    score += sum(
        1 for t in b_title_terms - a_terms if len(t) >= 6 and t in a_compact
    )
    return score


# --------------------------------------------------------------------------
# SQL helpers
# --------------------------------------------------------------------------
def _has_text(column):
    """SQL expression: column is not NULL and not blank/whitespace."""
    return func.length(func.trim(func.coalesce(column, ""))) > 0


def _content_filter():
    """Exclude resources without any meaningful content."""
    return or_(
        _has_text(Resource.title),
        _has_text(Resource.description),
        _has_text(Resource.extracted_text),
    )


# --------------------------------------------------------------------------
# Embeddings
# --------------------------------------------------------------------------
def build_embedding_text(resource: Resource) -> str:
    """Title + description + start of extracted text, with URLs removed."""
    parts = [
        _clean_text(resource.title),
        _clean_text(resource.description),
        _clean_text(resource.extracted_text)[:EMBED_TEXT_CHARS],
    ]
    return "\n".join(p for p in parts if p)


def ensure_embedding(
    resource: Resource,
    db: Session,
    embed_fn: Optional[EmbedFn],
    force: bool = False,
) -> bool:
    """
    Make sure the resource has an embedding, generating one if needed.
    With force=True the embedding is regenerated even if one exists.
    Returns True if the resource has an embedding afterwards.
    """
    if resource.embedding is not None and not force:
        return True

    if embed_fn is None:
        return resource.embedding is not None

    text = build_embedding_text(resource)
    if not text:
        return resource.embedding is not None

    try:
        resource.embedding = list(embed_fn(text))
        db.add(resource)
        db.commit()
        db.refresh(resource)
        return True
    except Exception:
        db.rollback()
        logger.exception("Failed to embed resource %s", resource.id)
        return False


# --------------------------------------------------------------------------
# Keyword fallback (no usable embedding)
# --------------------------------------------------------------------------
def _keyword_fallback(
    resource: Resource,
    user_id: int,
    db: Session,
    limit: int,
) -> List[Resource]:
    """Rank the user's other resources by shared keywords with this one."""
    if not _keywords(resource.title):
        return []

    candidates = (
        db.query(Resource)
        .filter(
            Resource.user_id == user_id,
            Resource.id != resource.id,
            _content_filter(),
        )
        .limit(300)
        .all()
    )

    scored = [(r, _keyword_score(resource, r)) for r in candidates]
    scored = [(r, s) for r, s in scored if s > 0]
    scored.sort(key=lambda item: item[1], reverse=True)

    return [r for r, _ in scored[:limit]]


# --------------------------------------------------------------------------
# Main API
# --------------------------------------------------------------------------
def find_related_resources(
    resource_id: int,
    user_id: int,
    db: Session,
    limit: int = 5,
    embed_fn: Optional[EmbedFn] = None,
    strict_distance: float = STRICT_DISTANCE,
    loose_distance: float = LOOSE_DISTANCE,
    relative_margin: Optional[float] = RELATIVE_MARGIN,
) -> Optional[List[Resource]]:
    """
    Return resources related to the given resource.

    Returns:
        None  -> the resource does not exist for this user
        []    -> nothing related found
        list  -> related resources, best first
    """
    # 1. Find the selected resource belonging to the current user.
    resource = (
        db.query(Resource)
        .filter(
            Resource.id == resource_id,
            Resource.user_id == user_id,
        )
        .first()
    )

    if resource is None:
        return None

    # 2. No embedding? Try to create one; otherwise use the keyword fallback.
    if not ensure_embedding(resource, db, embed_fn):
        logger.debug(
            "Resource %s has no embedding; using keyword fallback", resource_id
        )
        return _keyword_fallback(resource, user_id, db, limit)

    # 3. Build the distance expression once and reuse it.
    distance = Resource.embedding.cosine_distance(resource.embedding)

    # 4. Nearest candidates under the loose ceiling.
    rows = (
        db.query(Resource, distance.label("cosine_distance"))
        .filter(
            Resource.user_id == user_id,
            Resource.id != resource_id,
            Resource.embedding.is_not(None),
            distance <= loose_distance,
            _content_filter(),
        )
        .order_by(distance.asc())
        .limit(limit * CANDIDATE_MULTIPLIER)
        .all()
    )

    # 5. Accept: very close, OR reasonably close with a shared keyword.
    accepted: List[Tuple[Resource, float]] = []
    for related, dist in rows:
        d = float(dist)
        score = _keyword_score(resource, related)
        keep = d <= strict_distance or (d <= loose_distance and score > 0)
        logger.debug(
            "%s (%r) vs %s (%r): distance=%.3f keywords=%d -> %s",
            resource_id,
            resource.title,
            related.id,
            related.title,
            d,
            score,
            "keep" if keep else "drop",
        )
        if keep:
            accepted.append((related, d))

    # 6. Nothing passed: fall back to keywords only.
    if not accepted:
        return _keyword_fallback(resource, user_id, db, limit)

    # 7. Relative cutoff against the best ACCEPTED match.
    if relative_margin is not None:
        best = accepted[0][1]
        accepted = [(r, d) for r, d in accepted if d <= best + relative_margin]

    return [r for r, _ in accepted[:limit]]


# --------------------------------------------------------------------------
# Maintenance / diagnostics
# --------------------------------------------------------------------------
def backfill_missing_embeddings(
    user_id: int,
    db: Session,
    embed_fn: EmbedFn,
    force: bool = False,
) -> Tuple[int, int]:
    """
    Embed this user's resources.

    force=False -> only resources with no embedding yet.
    force=True  -> regenerate ALL embeddings (do this once after changing
                   build_embedding_text, e.g. the URL cleaning added here).

    Returns (embedded_count, failed_count).
    """
    query = db.query(Resource.id).filter(
        Resource.user_id == user_id,
        _content_filter(),
    )
    if not force:
        query = query.filter(Resource.embedding.is_(None))

    resource_ids = [rid for (rid,) in query.all()]

    embedded = failed = 0
    for rid in resource_ids:
        resource = db.query(Resource).filter(Resource.id == rid).first()
        if resource is None:
            continue
        if ensure_embedding(resource, db, embed_fn, force=force):
            embedded += 1
        else:
            failed += 1

    return embedded, failed


def debug_resource_distances(
    resource_id: int,
    user_id: int,
    db: Session,
    limit: int = 15,
) -> List[Tuple[int, str, float, int]]:
    """
    Nearest neighbours with NO threshold, as (id, title, distance, keywords).
    Use it to see the real numbers and tune STRICT/LOOSE_DISTANCE.

        for rid, title, d, kw in debug_resource_distances(42, user_id, db):
            print(f"{d:.3f}  kw={kw}  {rid}  {title}")
    """
    resource = (
        db.query(Resource)
        .filter(
            Resource.id == resource_id,
            Resource.user_id == user_id,
        )
        .first()
    )

    if resource is None or resource.embedding is None:
        return []

    distance = Resource.embedding.cosine_distance(resource.embedding)

    rows = (
        db.query(Resource, distance.label("cosine_distance"))
        .filter(
            Resource.user_id == user_id,
            Resource.id != resource_id,
            Resource.embedding.is_not(None),
        )
        .order_by(distance.asc())
        .limit(limit)
        .all()
    )

    return [
        (r.id, r.title, float(d), _keyword_score(resource, r)) for r, d in rows
    ]