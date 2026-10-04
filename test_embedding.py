from app.services.embedding_service import generate_embedding


text = "FastAPI JWT authentication using Python"


embedding = generate_embedding(text)


print("Embedding generated successfully!")
print("Number of dimensions:", len(embedding))
print("First 10 values:", embedding[:10])