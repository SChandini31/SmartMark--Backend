"""
Compare embedding models on your own data WITHOUT changing the database.

For each model it embeds the query and the chunks of a few documents, then
prints the best similarity per document. A model is better for you if the
document that should match (62) scores clearly higher than the ones that
should not (Java, DSA, quantum computing).

Run from the backend folder:  python check_models.py
"""

from sentence_transformers import SentenceTransformer

from app.db.database import SessionLocal
from app.models.document_chunk import DocumentChunk

QUERY = "microcontroller"          # also try "microcontroller programming"

RELEVANT = [62, 65]                # should match (IoT lab doc, Arduino page)
IRRELEVANT = [21, 15, 71, 25, 29]  # should not (Java, DSA, quantum computing)

MAX_CHUNKS = 80                    # chunks per document, keeps it fast

# (model name, query prefix, passage prefix)
# Delete a line if you do not want to download that model.
MODELS = [
    ("sentence-transformers/all-MiniLM-L6-v2", "", ""),
    ("sentence-transformers/multi-qa-MiniLM-L6-cos-v1", "", ""),
    (
        "BAAI/bge-small-en-v1.5",
        "Represent this sentence for searching relevant passages: ",
        "",
    ),
]


def load_chunks(db, resource_id):
    rows = (
        db.query(DocumentChunk.content)
        .filter(
            DocumentChunk.resource_id == resource_id,
            DocumentChunk.content.is_not(None),
        )
        .order_by(DocumentChunk.chunk_index)
        .limit(MAX_CHUNKS)
        .all()
    )
    return [row[0] for row in rows]


def main():
    db = SessionLocal()

    chunks = {
        rid: load_chunks(db, rid) for rid in RELEVANT + IRRELEVANT
    }

    print(f'Query: "{QUERY}"\n')

    for name, query_prefix, passage_prefix in MODELS:
        model = SentenceTransformer(name)

        query_vec = model.encode(
            query_prefix + QUERY,
            normalize_embeddings=True,
        )

        best = {}

        for rid, texts in chunks.items():
            if not texts:
                best[rid] = None
                continue

            vecs = model.encode(
                [passage_prefix + t for t in texts],
                normalize_embeddings=True,
            )
            best[rid] = float((vecs @ query_vec).max())

        print(name)
        for rid in RELEVANT:
            print(f"  should match   {rid}: {best[rid]}")
        for rid in IRRELEVANT:
            print(f"  should not     {rid}: {best[rid]}")

        hard = best.get(62)
        wrong = [best[r] for r in IRRELEVANT if best[r] is not None]

        if hard is not None and wrong:
            print(f"  margin (doc 62 minus best wrong doc): {hard - max(wrong):+.3f}\n")

    db.close()


if __name__ == "__main__":
    main()