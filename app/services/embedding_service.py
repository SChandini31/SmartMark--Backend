from sentence_transformers import SentenceTransformer


# Load the embedding model once when the application starts.
# all-MiniLM-L6-v2 produces 384-dimensional embeddings.
model = SentenceTransformer("all-MiniLM-L6-v2")


def generate_embedding(text: str) -> list[float]:
    """
    Generate a 384-dimensional embedding for the given text.
    """

    if not text or not text.strip():
        raise ValueError("Text cannot be empty")

    embedding = model.encode(
        text,
        convert_to_numpy=True
    )

    return embedding.tolist()