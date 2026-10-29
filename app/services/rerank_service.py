import math

from sentence_transformers import CrossEncoder

# Small cross-encoder trained for passage ranking (about 90 MB, downloaded
# once on first use, like your MiniLM model).
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Loaded only when the first search needs it.
_model = None


def get_reranker():
    global _model

    if _model is None:
        _model = CrossEncoder(RERANK_MODEL)

    return _model


def rerank_scores(query: str, passages: list[str]) -> list[float]:
    """
    Score how relevant each passage is to the query, from 0.0 to 1.0.

    A cross-encoder reads the query and the passage together, so it can
    tell that a Java tutorial is not about microcontrollers even though
    both mention "programming".
    """
    if not passages:
        return []

    model = get_reranker()

    raw = model.predict([(query, passage) for passage in passages])
    scores = [float(s) for s in raw]

    # Some library versions return probabilities, others raw logits.
    # Convert only when the values are clearly logits.
    if any(s < 0.0 or s > 1.0 for s in scores):
        scores = [1.0 / (1.0 + math.exp(-s)) for s in scores]

    return scores