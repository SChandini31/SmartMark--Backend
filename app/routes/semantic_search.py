import difflib
import math
import re
import time
from collections import Counter
from functools import lru_cache

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.models.resource import Resource
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.resource import ResourceResponse
from app.routes.search import (
    search_resources as keyword_search_resources,
)
from app.services.semantic_search_service import (
    semantic_search,
    semantic_search_with_passages,
)

router = APIRouter(
    prefix="/api/search",
    tags=["Semantic Search"],
)

# ---------------------------------------------------------
# Tunables
# ---------------------------------------------------------

# Set to True to print scoring details to the terminal.
SEARCH_DEBUG = False

LEXICAL_WEIGHT = 0.35
SEMANTIC_WEIGHT = 0.65

# Results scoring below this are dropped.
MIN_FINAL_SCORE = 0.08

# A result with no semantic match must contain all the informative
# query terms (a partial match scores at most 0.35).
MIN_KEYWORD_ONLY_LEXICAL = 0.50

# Results scoring below this fraction of the best result are dropped.
# Applied to the HYBRID scores, before any reranking.
RELATIVE_SCORE_CUTOFF = 0.50

# Terms shorter than this use word-boundary regex instead of ILIKE substring.
SHORT_TERM_LEN = 5

# Automatic query expansion (pseudo-relevance feedback).
# Distinctive words are learned from the top matches and only BOOST
# documents that already matched; they never admit new ones.
FEEDBACK_DOCS = 3
FEEDBACK_CANDIDATES = 10
FEEDBACK_TERMS = 3
FEEDBACK_MAX_DF_RATIO = 0.30
FEEDBACK_MIN_DF = 2
EXPANSION_WEIGHT = 0.25

# Optional cross-encoder reranker. OFF by default: on this library its
# scores were erratic (0.93 for one Java page, 0.0004 for another) and it
# hurt more than it helped. If you turn it on, it only REORDERS the top
# results; it can never remove one.
RERANK_TOP_N = 0           # 0 = off
RERANK_WEIGHT = 0.30
RERANK_PASSAGE_CHARS = 600

# Per-user index (vocabulary + document frequencies) cache.
INDEX_TTL_SECONDS = 300
_INDEX_CACHE = {}

# Words ignored when learning expansion terms.
STOPWORDS = {
    "about", "above", "after", "again", "against", "also", "among", "because",
    "been", "before", "being", "below", "between", "both", "build", "can",
    "could", "does", "doing", "down", "during", "each", "even", "every",
    "from", "further", "have", "having", "here", "hers", "himself", "into",
    "itself", "just", "learn", "like", "make", "more", "most", "much", "must",
    "only", "other", "ours", "over", "same", "should", "since", "some",
    "such", "than", "that", "their", "theirs", "them", "then", "there",
    "these", "they", "this", "those", "through", "under", "until", "upon",
    "using", "used", "very", "want", "were", "what", "when", "where",
    "which", "while", "will", "with", "within", "without", "would", "your",
    "yours", "https", "http", "html", "page", "pages", "share", "click",
    "menu", "home", "sign", "login", "free", "course", "courses",
    "tutorial", "tutorials", "guide", "introduction", "overview",
}

# Question filler that carries no search value ("how to ...", "what is ...").
# Removed from keyword matching and lexical scoring only; the semantic
# search still sees the full question.
QUERY_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were",
    "be", "been", "being", "am", "do", "does", "did",
    "has", "have", "had", "to", "of", "in", "on",
    "at", "for", "from", "by", "with", "about",
    "and", "or", "but", "if", "as", "it", "its",
    "this", "that", "these", "those", "what", "which",
    "who", "whom", "how", "when", "where", "why",
    "can", "could", "should", "would", "will",
    "i", "you", "he", "she", "we", "they",
    "my", "your", "our", "their", "me", "us",
    "please",
}


def debug(*args):
    if SEARCH_DEBUG:
        print(*args)


# ---------------------------------------------------------
# Shared normalization helpers
# ---------------------------------------------------------

def normalize(value):
    """Normalize case and repeated whitespace."""
    return " ".join((value or "").casefold().split())


def compact_text(value):
    """Remove spaces and punctuation for compact matching."""
    return re.sub(r"[^a-z0-9]+", "", normalize(value))


def tokenize(value):
    """Extract lowercase alphanumeric words."""
    return re.findall(r"[a-z0-9]+", normalize(value))


@lru_cache(maxsize=200000)
def stem(word):
    """
    Very light stemmer, so that "language" matches "languages" and
    "program" matches "programs", "programming" and "programmer".

    It is applied to BOTH the query and the document text, so small
    imperfections do not matter as long as both sides agree. It never
    changes words shorter than 4 letters or words containing digits.
    """
    if len(word) < 4 or not word.isalpha():
        return word

    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"

    if word.endswith(("sses", "ches", "shes", "xes", "zes")):
        word = word[:-2]
    elif word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]

    for suffix in ("ing", "ed", "er"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            word = word[:-len(suffix)]

            # programm -> program, runn -> run (but keep ll, ss, zz)
            if len(word) >= 2 and word[-1] == word[-2] and word[-1] not in "lsz":
                word = word[:-1]

            break

    return word


def segment_compact_query(compact_query, vocabulary):
    """
    Infer word boundaries in unspaced queries using the
    vocabulary found in the current user's saved resources.
    """
    if not compact_query:
        return []

    length = len(compact_query)
    best = [None] * (length + 1)
    best[0] = (0, [])

    for start in range(length):
        if best[start] is None:
            continue

        current_score, current_words = best[start]

        for end in range(start + 2, length + 1):
            word = compact_query[start:end]

            if word not in vocabulary:
                continue

            score = current_score + len(word) ** 2

            if best[end] is None or score > best[end][0]:
                best[end] = (score, current_words + [word])

    if best[length] is not None:
        return best[length][1]

    # Still supports exact compact phrase matching.
    return [compact_query]


def correct_token(token, vocabulary):
    """
    Fix a likely typo by picking the closest word from the user's own
    vocabulary (e.g. "microcontrolller" -> "microcontroller").
    Only used for tokens that are not already known words.
    """
    if token in vocabulary or len(token) < 6:
        return token

    candidates = [
        w for w in vocabulary
        if w and w[0] == token[0] and abs(len(w) - len(token)) <= 2
    ]

    match = difflib.get_close_matches(token, candidates, n=1, cutoff=0.85)

    return match[0] if match else token


def resolve_terms(raw_query, vocabulary):
    """
    Turn the raw query into clean search terms while keeping the
    spaces the user typed.

    - known word      -> kept
    - typo            -> corrected from the vocabulary
    - unspaced words  -> split ("reacthooks" -> react, hooks)
    """
    terms = []

    for token in tokenize(raw_query):
        if token in vocabulary:
            terms.append(token)
            continue

        corrected = correct_token(token, vocabulary)

        if corrected != token:
            terms.append(corrected)
            continue

        parts = segment_compact_query(token, vocabulary)

        if len(parts) > 1:
            terms.extend(parts)
        else:
            terms.append(token)

    return terms


def suspicious_fragmentation(resolved, original):
    """
    True when a word was shattered into three or more small fragments
    ("programming" -> pro, gram, ming). In that case the original words
    are safer than the split.
    """
    if not resolved or not original:
        return False

    if len(resolved) <= len(original):
        return False

    for word in original:
        if len(word) < 5:
            continue

        fragments = [term for term in resolved if term and term in word]

        if len(fragments) >= 3 and "".join(fragments) == word:
            return True

    return False


# ---------------------------------------------------------
# Per-user index: vocabulary + document frequency
# ---------------------------------------------------------

def _build_user_index(db, user_id):
    rows = (
        db.query(
            Resource.title,
            Resource.description,
            Resource.url,
            Resource.source_domain,
            Resource.original_filename,
            Resource.extracted_text,
        )
        .filter(Resource.user_id == user_id)
        .all()
    )

    vocabulary = set()
    doc_freq = Counter()

    for row in rows:
        doc_tokens = set()

        for value in row:
            doc_tokens.update(tokenize(value))

        vocabulary.update(doc_tokens)
        doc_freq.update(doc_tokens)

    chunk_rows = (
        db.query(DocumentChunk.content)
        .join(Resource, DocumentChunk.resource_id == Resource.id)
        .filter(
            Resource.user_id == user_id,
            DocumentChunk.content.is_not(None),
        )
        .all()
    )

    for (content,) in chunk_rows:
        vocabulary.update(tokenize(content))

    return {
        "vocabulary": vocabulary,
        "doc_freq": doc_freq,
        "n_docs": len(rows),
    }


def get_user_index(db, user_id):
    """Vocabulary and document frequencies, cached for a few minutes."""
    now = time.time()
    cached = _INDEX_CACHE.get(user_id)

    if cached and now - cached[0] < INDEX_TTL_SECONDS:
        return cached[1]

    index = _build_user_index(db, user_id)
    _INDEX_CACHE[user_id] = (now, index)
    return index


def invalidate_user_index(user_id):
    """Call this after a resource is added, updated or deleted."""
    _INDEX_CACHE.pop(user_id, None)


# ---------------------------------------------------------
# Automatic query expansion (pseudo-relevance feedback)
# ---------------------------------------------------------

def feedback_terms(feedback_texts, query_terms, doc_freq, n_docs):
    """
    Pick distinctive words that the top results share.

    - words must appear in at least 2 feedback documents; with fewer than
      2 trusted documents no expansion is done
    - generic words are removed with a stopword list and a document
      frequency limit, so this works for any topic without hard-coding
    """
    if len(feedback_texts) < 2 or n_docs == 0:
        return []

    query_stems = {stem(t) for t in query_terms}
    token_lists = []

    for text in feedback_texts:
        token_lists.append([
            t for t in tokenize(text)
            if len(t) >= 4
            and t.isalpha()
            and t not in STOPWORDS
            and stem(t) not in query_stems
        ])

    counters = [Counter(tokens) for tokens in token_lists]

    all_words = set()
    for counter in counters:
        all_words.update(counter)

    scores = {}

    for word in all_words:
        docs_with_word = sum(1 for c in counters if word in c)

        if docs_with_word < 2:
            continue

        df = doc_freq.get(word, 0)

        if df < FEEDBACK_MIN_DF or df / n_docs > FEEDBACK_MAX_DF_RATIO:
            continue

        idf = math.log((n_docs + 1) / (df + 1))

        tf = sum(
            counter[word] / max(len(tokens), 1)
            for counter, tokens in zip(counters, token_lists)
        )

        scores[word] = tf * idf * docs_with_word

    ranked_words = sorted(scores.items(), key=lambda item: -item[1])

    return [word for word, _ in ranked_words[:FEEDBACK_TERMS]]


def clean_passage(passage):
    """Remove repeated lines and collapse whitespace (display only)."""
    if not passage:
        return ""

    seen_lines = set()
    unique_lines = []

    for line in passage.splitlines():
        cleaned = " ".join(line.split())

        if not cleaned:
            continue

        key = normalize(cleaned)

        if key in seen_lines:
            continue

        seen_lines.add(key)
        unique_lines.append(cleaned)

    return " ".join(unique_lines)


def empty_response(query, resolved):
    return {
        "query": query,
        "resolved_query": resolved,
        "expanded_with": [],
        "total": 0,
        "results": [],
    }


# ---------------------------------------------------------
# Semantic-only search
# ---------------------------------------------------------

@router.get("/semantic")
def semantic_search_endpoint(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query_text = normalize(q)

    matches = semantic_search(
        query_text=query_text,
        user_id=current_user.id,
        db=db,
        limit=limit,
    )

    results = []

    for resource, distance in matches:
        resource_data = ResourceResponse.model_validate(
            resource,
            from_attributes=True,
        ).model_dump(exclude={"extracted_text"})

        resource_data["similarity_score"] = round(1.0 - float(distance), 4)
        results.append(resource_data)

    return results


# ---------------------------------------------------------
# Hybrid search
# ---------------------------------------------------------

@router.get("/hybrid")
def hybrid_search_endpoint(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    original_query = " ".join(q.split()).strip()

    if not original_query:
        return empty_response(q, "")

    # ---------------------------------------------------------
    # 1. Resolve query terms.
    # ---------------------------------------------------------

    index = get_user_index(db, current_user.id)
    vocabulary = index["vocabulary"]

    original_tokens = tokenize(original_query)
    terms = resolve_terms(original_query, vocabulary) or original_tokens

    if suspicious_fragmentation(terms, original_tokens):
        terms = original_tokens

    terms = [t.strip().lower() for t in terms if t and t.strip()]

    if not terms:
        return empty_response(original_query, original_query)

    # The semantic search sees the full resolved question.
    query_text = " ".join(terms)
    unique_terms = list(dict.fromkeys(terms))

    # Keyword matching and lexical scoring ignore question filler.
    informative_terms = [t for t in unique_terms if t not in QUERY_STOPWORDS]

    # If every term is generic, keep them rather than search for nothing.
    scoring_terms = informative_terms or unique_terms

    scoring_query = " ".join(scoring_terms)
    normalized_scoring_query = normalize(scoring_query)
    compact_scoring_query = compact_text(normalized_scoring_query)

    debug("\n========== HYBRID SEARCH DEBUG ==========")
    debug("Original query:", original_query)
    debug("Resolved query:", query_text)
    debug("Scoring terms:", scoring_terms)

    # ---------------------------------------------------------
    # 2. Retrieve semantic candidates.
    # ---------------------------------------------------------

    semantic_matches = semantic_search_with_passages(
        query_text=query_text,
        user_id=current_user.id,
        db=db,
        limit=50,
    )

    semantic_by_id = {}

    for resource, distance, chunk in semantic_matches:
        distance = float(distance)
        existing = semantic_by_id.get(resource.id)

        # Keep only the best semantic match per resource.
        if existing is None or distance < existing["distance"]:
            semantic_by_id[resource.id] = {
                "distance": distance,
                "chunk": chunk,
            }

    semantic_ids = set(semantic_by_id)

    candidates = {resource.id: resource for resource, _, _ in semantic_matches}

    debug("Semantic candidates:", len(semantic_by_id))

    # ---------------------------------------------------------
    # 3. Pseudo-relevance feedback.
    # ---------------------------------------------------------

    feedback_texts = []
    query_stem_set = {stem(t) for t in scoring_terms}

    for resource, _, chunk in semantic_matches[:FEEDBACK_CANDIDATES]:
        if len(feedback_texts) >= FEEDBACK_DOCS:
            break

        full_text = f"{resource.title or ''} {resource.extracted_text or ''}"

        # Do not expand the query using weak matches.
        document_stems = {stem(t) for t in tokenize(full_text)}

        if not query_stem_set.issubset(document_stems):
            continue

        body = (
            chunk.content
            if chunk is not None and chunk.content
            else (resource.extracted_text or "")[:1500]
        )

        feedback_texts.append(f"{resource.title or ''} {body}")

    original_word_set = set(original_tokens)
    original_stem_set = {stem(t) for t in original_tokens}

    expansion_terms = []

    for term in feedback_terms(
        feedback_texts,
        scoring_terms,
        index["doc_freq"],
        index["n_docs"],
    ):
        term = str(term).strip().lower()

        if (
            term
            and term not in original_word_set
            and stem(term) not in original_stem_set
            and term not in QUERY_STOPWORDS
            and len(term) >= 3
            and term.isalnum()
            and term not in expansion_terms
        ):
            expansion_terms.append(term)

    debug("Expansion terms:", expansion_terms)

    # ---------------------------------------------------------
    # 4. Retrieve keyword candidates.
    # ---------------------------------------------------------

    fields = [
        Resource.title,
        Resource.description,
        Resource.url,
        Resource.source_domain,
        Resource.original_filename,
        Resource.extracted_text,
    ]

    term_conditions = []

    # Informative terms only, so "a" or "the" don't match everything.
    for term in scoring_terms:
        escaped_term = re.escape(term)

        # Search by stem so "language" also finds "languages". Final
        # scoring compares stems too, so loose candidates are filtered later.
        term_stem = stem(term)

        for field in fields:
            if len(term) < SHORT_TERM_LEN:
                # Word-boundary match on Postgres: "iot" must not hit "riot".
                term_conditions.append(
                    field.op("~*")(rf"\y{escaped_term}s?\y")
                )
            else:
                term_conditions.append(field.ilike(f"%{term_stem}%"))

    compact_conditions = []

    if len(compact_scoring_query) >= SHORT_TERM_LEN:
        for field in fields:
            compact_conditions.append(
                func.regexp_replace(
                    func.lower(func.coalesce(field, "")),
                    r"[^a-z0-9]+",
                    "",
                    "g",
                ).ilike(f"%{compact_scoring_query}%")
            )

    conditions = term_conditions + compact_conditions
    keyword_candidates = []

    if conditions:
        keyword_candidates = (
            db.query(Resource)
            .filter(
                Resource.user_id == current_user.id,
                or_(*conditions),
            )
            .all()
        )

    keyword_ids = set()

    for resource in keyword_candidates:
        candidates[resource.id] = resource
        keyword_ids.add(resource.id)

    # Preserve the existing keyword-search integration.
    keyword_data = keyword_search_resources(
        q=scoring_query,
        resource_type=None,
        collection_id=None,
        sort_by="newest",
        page=1,
        limit=100,
        db=db,
        current_user=current_user,
    )

    for item in keyword_data.get("results", []):
        resource_ref = item["resource"]

        # The keyword route may return a dict or a database object.
        resource_id = (
            resource_ref["id"]
            if isinstance(resource_ref, dict)
            else resource_ref.id
        )

        if resource_id not in candidates:
            found = (
                db.query(Resource)
                .filter(
                    Resource.id == resource_id,
                    Resource.user_id == current_user.id,
                )
                .first()
            )

            if found is None:
                continue

            candidates[resource_id] = found

        keyword_ids.add(resource_id)

    debug("Keyword candidates:", len(keyword_candidates))
    debug("Unique candidates:", len(candidates))

    # ---------------------------------------------------------
    # 5. Load and deduplicate document chunks.
    # ---------------------------------------------------------

    resource_ids = list(candidates)
    chunks_by_resource = {}

    if resource_ids:
        chunk_rows = (
            db.query(
                DocumentChunk.resource_id,
                DocumentChunk.content,
                DocumentChunk.chunk_index,
            )
            .filter(
                DocumentChunk.resource_id.in_(resource_ids),
                DocumentChunk.content.is_not(None),
            )
            .order_by(
                DocumentChunk.resource_id,
                DocumentChunk.chunk_index,
            )
            .all()
        )

        seen_by_resource = {}

        for row in chunk_rows:
            content = row.content

            if not content or not content.strip():
                continue

            # Duplicate detection ignores case and whitespace;
            # the original passage is kept for display.
            key = normalize(content)

            seen = seen_by_resource.setdefault(row.resource_id, set())

            if key in seen:
                continue

            seen.add(key)
            chunks_by_resource.setdefault(row.resource_id, []).append(content)

    # ---------------------------------------------------------
    # 6. IDF weights: rare query words count more than common ones.
    # ---------------------------------------------------------

    n_docs_total = max(index["n_docs"], 1)

    term_weights = {
        term: (
            math.log((n_docs_total + 1) / (index["doc_freq"].get(term, 0) + 1))
            + 0.1
        )
        for term in scoring_terms
    }

    total_weight = sum(term_weights.values()) or 1.0

    # Matching works on stems, so "language" matches "languages" and
    # "programming" matches "programs" and "programmer".
    term_stems = {term: stem(term) for term in scoring_terms}

    terms_by_stem = {}

    for term, term_stem in term_stems.items():
        terms_by_stem.setdefault(term_stem, []).append(term)

    stemmed_scoring_query = " ".join(term_stems[term] for term in scoring_terms)

    phrase_pattern = re.compile(
        rf"(?<![a-z0-9]){re.escape(stemmed_scoring_query)}(?![a-z0-9])"
    )

    # ---------------------------------------------------------
    # 7. Score a passage using informative terms.
    # ---------------------------------------------------------

    def score_passage(passage):
        text = normalize(passage or "")

        if not text:
            return 0.0

        word_matches = list(re.finditer(r"[a-z0-9]+", text))
        stemmed_words = [stem(m.group()) for m in word_matches]

        positions_by_term = {term: [] for term in scoring_terms}

        for match, stemmed in zip(word_matches, stemmed_words):
            for term in terms_by_stem.get(stemmed, ()):
                positions_by_term[term].append(match.start())

        matched_terms = [
            term for term, positions in positions_by_term.items() if positions
        ]

        if not matched_terms:
            return 0.0

        coverage = (
            sum(term_weights[term] for term in matched_terms) / total_weight
        )

        # Whole-word phrase match on stems: "java" must not match
        # "javascript", but "programming language" matches
        # "programming languages".
        phrase_match = bool(phrase_pattern.search(" ".join(stemmed_words))) or (
            len(compact_scoring_query) >= SHORT_TERM_LEN
            and compact_scoring_query in compact_text(text)
        )

        if phrase_match:
            # Strong evidence, but not an automatic perfect score.
            return 0.80 + 0.15 * coverage

        # Partial matches receive a conservative score.
        if len(matched_terms) < len(scoring_terms):
            return 0.35 * coverage

        # Smallest window that contains every informative term.
        all_positions = sorted(
            (position, term)
            for term, positions in positions_by_term.items()
            for position in positions
        )

        counts = Counter()
        left = 0
        matched_count = 0
        best_span = None

        for position, term in all_positions:
            if counts[term] == 0:
                matched_count += 1

            counts[term] += 1

            while matched_count == len(scoring_terms):
                span = position - all_positions[left][0]

                if best_span is None or span < best_span:
                    best_span = span

                left_term = all_positions[left][1]
                counts[left_term] -= 1

                if counts[left_term] == 0:
                    matched_count -= 1

                left += 1

        span = best_span if best_span is not None else 1000
        proximity = 1.0 / (1.0 + span / 40.0)

        return 0.65 + 0.30 * proximity

    # ---------------------------------------------------------
    # 8. Score candidates using lexical and semantic relevance.
    # ---------------------------------------------------------

    ranked = []

    for resource in candidates.values():
        semantic_entry = semantic_by_id.get(resource.id)

        passages = list(chunks_by_resource.get(resource.id, []))
        seen_passages = {normalize(p) for p in passages}

        if semantic_entry is not None:
            matching_chunk = semantic_entry["chunk"]

            if matching_chunk is not None and matching_chunk.content:
                matching_key = normalize(matching_chunk.content)

                if matching_key and matching_key not in seen_passages:
                    passages.append(matching_chunk.content)
                    seen_passages.add(matching_key)

        if not passages and resource.extracted_text:
            # No stored chunks: split the text into passages instead.
            for start in range(0, len(resource.extracted_text), 1000):
                passage = resource.extracted_text[start:start + 1000]
                key = normalize(passage)

                if key and key not in seen_passages:
                    seen_passages.add(key)
                    passages.append(passage)

        best_passage = None
        passage_score = 0.0

        for passage in passages:
            current_score = score_passage(passage)

            if current_score > passage_score:
                passage_score = current_score
                best_passage = passage

        original_lexical = max(
            passage_score,
            score_passage(resource.title or ""),
            score_passage(resource.description or ""),
        )

        lexical_score = original_lexical

        # Expansion terms give a small boost only when the resource
        # already has original-query evidence.
        if original_lexical > 0 and expansion_terms:
            resource_text = normalize(
                " ".join(
                    part
                    for part in [
                        resource.title,
                        resource.description,
                        resource.url,
                        resource.source_domain,
                        resource.original_filename,
                        resource.extracted_text,
                        *chunks_by_resource.get(resource.id, []),
                    ]
                    if part
                )
            )

            hits = [
                term
                for term in expansion_terms
                if re.search(rf"\b{re.escape(term)}\b", resource_text)
            ]

            if hits:
                lexical_score = min(
                    1.0,
                    original_lexical
                    + EXPANSION_WEIGHT * len(hits) / len(expansion_terms),
                )

        semantic_score = (
            max(0.0, min(1.0, 1.0 - semantic_entry["distance"]))
            if semantic_entry is not None
            else 0.0
        )

        # Keyword-only results must contain all the informative terms.
        if (
            semantic_entry is None
            and original_lexical < MIN_KEYWORD_ONLY_LEXICAL
        ):
            continue

        final_score = (
            LEXICAL_WEIGHT * lexical_score
            + SEMANTIC_WEIGHT * semantic_score
        )

        if final_score < MIN_FINAL_SCORE:
            continue

        ranked.append((final_score, resource, semantic_entry, best_passage))

    ranked.sort(key=lambda item: item[0], reverse=True)

    debug("Ranked before cutoff:", len(ranked))

    for score, resource, semantic_entry, best_passage in ranked:
        debug(
            "  ranked:", resource.id, resource.title,
            "score:", round(score, 4),
            "semantic distance:",
            round(semantic_entry["distance"], 4) if semantic_entry else None,
        )

    # ---------------------------------------------------------
    # 9. Relative cutoff on the HYBRID scores.
    #    Done before reranking so a reranker can never delete results.
    # ---------------------------------------------------------

    if ranked:
        cutoff = ranked[0][0] * RELATIVE_SCORE_CUTOFF
        before_cutoff = len(ranked)

        ranked = [item for item in ranked if item[0] >= cutoff]

        debug("Relative cutoff:", round(cutoff, 4))
        debug("Removed by relative cutoff:", before_cutoff - len(ranked))

    # ---------------------------------------------------------
    # 10. Optional cross-encoder reranking (reorders only).
    # ---------------------------------------------------------

    def rerank_text(resource, semantic_entry, best_passage):
        if best_passage:
            passage = best_passage
        elif (
            semantic_entry is not None
            and semantic_entry["chunk"] is not None
            and semantic_entry["chunk"].content
        ):
            passage = semantic_entry["chunk"].content
        elif chunks_by_resource.get(resource.id):
            passage = chunks_by_resource[resource.id][0]
        else:
            passage = resource.extracted_text or resource.description or ""

        # Keep the header short so the passage always gets room.
        header = f"{resource.title or ''}. {resource.description or ''}."[:200]

        return f"{header} {clean_passage(passage)}"[:RERANK_PASSAGE_CHARS]

    if len(ranked) > 1 and RERANK_TOP_N > 0:
        top_candidates = ranked[:RERANK_TOP_N]
        remaining_candidates = ranked[RERANK_TOP_N:]

        try:
            from app.services.rerank_service import rerank_scores

            ce_scores = rerank_scores(
                query_text,
                [
                    rerank_text(resource, semantic_entry, best_passage)
                    for _, resource, semantic_entry, best_passage
                    in top_candidates
                ],
            )

            if len(ce_scores) != len(top_candidates):
                raise ValueError("Unexpected number of reranker scores")

            blended = []

            for candidate, ce in zip(top_candidates, ce_scores):
                original_score, resource, semantic_entry, best_passage = candidate

                ce = float(ce)

                if not math.isfinite(ce):
                    raise ValueError("Reranker returned a non-finite score")

                blended.append((
                    RERANK_WEIGHT * ce + (1.0 - RERANK_WEIGHT) * original_score,
                    resource,
                    semantic_entry,
                    best_passage,
                ))

            blended.sort(key=lambda item: item[0], reverse=True)
            ranked = blended + remaining_candidates

            debug("Reranking applied to:", len(blended))

        except Exception as error:
            # If the reranker fails, keep the hybrid order.
            print(f"Reranker unavailable; using hybrid scores: {error}")

    debug("Final result count:", min(len(ranked), limit))
    debug("========== END HYBRID SEARCH DEBUG ==========\n")

    # ---------------------------------------------------------
    # 11. Serialize results.
    # ---------------------------------------------------------

    results = []

    for score, resource, semantic_entry, best_passage in ranked[:limit]:
        resource_data = ResourceResponse.model_validate(
            resource,
            from_attributes=True,
        ).model_dump(exclude={"extracted_text"})

        resource_data["hybrid_score"] = round(score, 4)

        resource_data["similarity_score"] = (
            round(1.0 - semantic_entry["distance"], 4)
            if semantic_entry is not None
            else None
        )

        matched_by = []

        if resource.id in keyword_ids:
            matched_by.append("keyword")

        if resource.id in semantic_ids:
            matched_by.append("semantic")

        resource_data["matched_by"] = matched_by

        snippet = clean_passage(best_passage)

        if snippet:
            if len(snippet) > 400:
                snippet = snippet[:400].rsplit(" ", 1)[0] + "..."
        else:
            snippet = (
                resource.title
                or resource.description
                or resource.original_filename
            )

        resource_data["snippet"] = snippet
        results.append(resource_data)

    return {
        "query": original_query,
        "resolved_query": query_text,
        "expanded_with": expansion_terms,
        "total": len(ranked),
        "results": results,
    }