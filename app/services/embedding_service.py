from sentence_transformers import SentenceTransformer


# Model is loaded only when an embedding is actually needed.
model = None


def get_model():
    global model

    if model is None:
        model = SentenceTransformer(
            "all-MiniLM-L6-v2",
            backend="onnx"
        )

    return model


def generate_embedding(text: str) -> list[float]:
    """
    Generate a 384-dimensional embedding for the given text.
    """

    if not text or not text.strip():
        raise ValueError("Text cannot be empty")

    embedding_model = get_model()

    embedding = embedding_model.encode(
        text,
        convert_to_numpy=True
    )

    return embedding.tolist()