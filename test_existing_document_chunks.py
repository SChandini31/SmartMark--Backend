
import re
from pathlib import Path

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.resource import Resource
from app.services.document_extraction_service import extract_text_from_file
from app.services.document_chunking_service import chunk_text


RESOURCE_ID = 62
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

EXPERIMENT_RE = re.compile(
    r"^\s*Experiment\s+\d+\s*:",
    re.IGNORECASE,
)

SUBEXPERIMENT_RE = re.compile(
    r"^\s*\d+\s*\([a-z]\)\s+\S",
    re.IGNORECASE,
)

SECTION_RE = re.compile(
    r"^\s*(Aim|Objective|Theory|Components|Apparatus|"
    r"Circuit connections|Procedure|Program|Code|"
    r"Expected output|Sample output|Observation|Result|"
    r"Conclusion|Notes?)\s*:?\s*(.*)$",
    re.IGNORECASE,
)

KNOWN_DOCUMENT_PATH = Path(
    r"C:\SmartMark--backend\uploads\documents"
    r"\5320e3a52fe04b8aa9638eff57547d90.docx"
)


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def locate_document(resource) -> Path | None:
    """Locate the original document without modifying the resource."""
    for attribute in (
        "file_path",
        "original_filename",
        "storage_path",
        "document_path",
    ):
        value = getattr(resource, attribute, None)

        if not value:
            continue

        candidate = Path(value)

        if candidate.is_file():
            return candidate

    if KNOWN_DOCUMENT_PATH.is_file():
        return KNOWN_DOCUMENT_PATH

    return None



def build_contextual_chunks(text, chunks):
    """Assign each chunk the document context active at its starting position."""
    experiment_re = re.compile(
        r"^\s*Experiment\s+\d+\s*:", re.IGNORECASE
    )
    subexperiment_re = re.compile(
        r"^\s*\d+\s*\([a-z]\)\s+\S", re.IGNORECASE
    )
    section_re = re.compile(
        r"^\s*(Aim|Objective|Theory|Components|Apparatus|"
        r"Circuit connections|Procedure|Program|Code|"
        r"Expected output|Sample output|Observation|"
        r"Result|Conclusion|Notes?)\s*:?(?:\s|$)",
        re.IGNORECASE,
    )

    # Record the starting position of every original line.
    source_lines = []
    position = 0
    for line in text.splitlines(keepends=True):
        source_lines.append((position, line))
        position += len(line)

    results = []
    chunk_start = 0
    line_index = 0

    experiment = None
    subexperiment = None
    section = None

    for chunk in chunks:
        # Update context only through the line where this chunk starts.
        while (
            line_index < len(source_lines)
            and source_lines[line_index][0] <= chunk_start
        ):
            _, line = source_lines[line_index]
            stripped = line.strip()

            if experiment_re.match(line):
                experiment = stripped
                subexperiment = None
                section = None

            elif subexperiment_re.match(line):
                subexperiment = stripped
                section = None

            else:
                match = section_re.match(line)
                if match:
                    section = match.group(1).title()

            line_index += 1

        context_parts = []

        if experiment:
            context_parts.append(experiment)

        if subexperiment:
            context_parts.append(subexperiment)

        if section:
            context_parts.append(f"Section: {section}")

        context = " | ".join(context_parts)

        # Keep the original chunk unchanged; add context only for embedding.
        
        if context:
            max_context_length = CHUNK_SIZE - len(chunk) - 1

            if len(context) > max_context_length:
                section_suffix = (
                    f" | Section: {section}" if section else ""
                )
                base = " | ".join(
                    part for part in (experiment, subexperiment)
                    if part
                )

                if section_suffix and len(section_suffix) <= max_context_length:
                    base_budget = max_context_length - len(section_suffix)

                    if len(base) > base_budget:
                        base = (
                            base[:max(0, base_budget - 3)].rstrip() + "..."
                            if base_budget >= 4
                            else ""
                        )

                    context = (
                        f"{base}{section_suffix}"
                        if base
                        else section_suffix.lstrip(" |")
                    )
                else:
                    context = context[:max_context_length]

            embedding_text = f"{context}\n{chunk}"
        else:
            embedding_text = chunk


        results.append({
            "content": chunk,
            "context": context,
            "embedding_text": embedding_text,
        })

        chunk_start += len(chunk)

    return results



def main():
    # Read resource metadata only; no database writes.
    with SessionLocal() as db:
        resource = db.execute(
            select(Resource).where(Resource.id == RESOURCE_ID)
        ).scalar_one_or_none()

        if resource is None:
            print(f"ERROR: Resource {RESOURCE_ID} not found.")
            return

        print(f"Resource ID: {resource.id}")
        print(f"Title: {resource.title}")

        file_path = locate_document(resource)

        if file_path is None:
            print("ERROR: Could not locate the document file.")
            print("Check the resource model's document path field.")
            return

        print(f"Stored file path: {file_path}")

    # Extract and normalize text using the existing extraction service.
    extracted_text = extract_text_from_file(str(file_path))

    if not extracted_text or not extracted_text.strip():
        print("ERROR: Document extraction returned no text.")
        return

    normalized_text = normalize_text(extracted_text)

    print(f"Extracted characters: {len(normalized_text)}")

    # Existing chunker: generate chunks in memory only.
    chunks = chunk_text(
        normalized_text,
        chunk_size=CHUNK_SIZE,
        overlap=CHUNK_OVERLAP,
    )

    if not chunks:
        print("ERROR: No chunks generated.")
        return

    # ---------------------------------------------------------
    # 1. Validate the original chunks.
    # ---------------------------------------------------------
    print("\n===== ORIGINAL CHUNK VALIDATION =====")

    oversized = [
        (index, len(chunk))
        for index, chunk in enumerate(chunks, start=1)
        if len(chunk) > CHUNK_SIZE
    ]

    reconstructed_text = "".join(chunks)
    content_preserved = reconstructed_text == normalized_text

    empty_chunks = [
        index
        for index, chunk in enumerate(chunks, start=1)
        if not chunk.strip()
    ]

    print(f"Original chunk count: {len(chunks)}")
    print(f"Largest original chunk: {max(map(len, chunks))}")
    print(f"Chunks exceeding {CHUNK_SIZE}: {len(oversized)}")
    print(f"Original characters: {len(normalized_text)}")
    print(f"Total chunk characters: {sum(map(len, chunks))}")
    print(f"Exact content preserved: {content_preserved}")
    print(f"Empty chunks: {len(empty_chunks)}")

    # ---------------------------------------------------------
    # 2. Build contextual embedding text without database writes.
    # ---------------------------------------------------------
    contextual_chunks = build_contextual_chunks(
        normalized_text,
        chunks,
    )

    print("\n===== CONTEXTUAL CHUNK VALIDATION =====")

    oversized_contextual = []
    missing_context = []
    program_chunk_count = 0

    for index, item in enumerate(contextual_chunks, start=1):
        content = item["content"]
        context = item["context"]
        embedding_text = item["embedding_text"]

        if len(embedding_text) > CHUNK_SIZE:
            oversized_contextual.append(
                (index, len(embedding_text))
            )

        is_program_chunk = bool(
            re.search(
                r"\bProgram\b|void\s+setup\s*\(|void\s+loop\s*\(",
                content,
                re.IGNORECASE,
            )
        )

        if is_program_chunk:
            program_chunk_count += 1

            if not context:
                missing_context.append(index)

        if (
            "void loop()" in content
            or "void setup()" in content
        ):
            print(f"\nChunk {index}")
            print(f"Original length: {len(content)}")
            print(f"Embedding length: {len(embedding_text)}")
            print(f"Context: {context or '(none)'}")
            print(
                "Embedding preview:",
                repr(embedding_text[:220]),
            )

    original_content_unchanged = all(
        item["content"] == chunk
        for item, chunk in zip(contextual_chunks, chunks)
    )

    print(f"\nContextual chunk count: {len(contextual_chunks)}")
    print(f"Program-related chunks: {program_chunk_count}")
    print(f"Program chunks missing context: {len(missing_context)}")
    print(
        "Embedding texts exceeding limit:",
        len(oversized_contextual),
    )
    print(
        "Original content unchanged:",
        original_content_unchanged,
    )

    if missing_context:
        print("Chunks missing context:", missing_context)

    if oversized_contextual:
        print("Oversized contextual chunks:", oversized_contextual)

    # ---------------------------------------------------------
    # 3. Print a compact contextual summary.
    # ---------------------------------------------------------
    print("\n===== CONTEXTUAL CHUNK SUMMARY =====")

    for index, item in enumerate(contextual_chunks, start=1):
        preview = " ".join(item["content"].split())[:90]
        context_preview = " | ".join(item["context"].splitlines())

        print(
            f"Chunk {index}: "
            f"content={len(item['content'])}, "
            f"embedding={len(item['embedding_text'])}, "
            f"context={context_preview!r}, "
            f"preview={preview!r}"
        )

    # ---------------------------------------------------------
    # 4. Final verdict.
    # ---------------------------------------------------------
    size_ok = not oversized
    content_ok = content_preserved
    nonempty_ok = not empty_chunks
    original_ok = original_content_unchanged
    context_ok = not missing_context
    embedding_size_ok = not oversized_contextual

    passed = all(
        (
            size_ok,
            content_ok,
            nonempty_ok,
            original_ok,
            context_ok,
            embedding_size_ok,
        )
    )

    print("\n===== FINAL VALIDATION =====")
    print(f"Original chunk sizes: {'PASS' if size_ok else 'FAIL'}")
    print(f"Exact content preservation: {'PASS' if content_ok else 'FAIL'}")
    print(f"Non-empty chunks: {'PASS' if nonempty_ok else 'FAIL'}")
    print(f"Original content unchanged: {'PASS' if original_ok else 'FAIL'}")
    print(f"Program context present: {'PASS' if context_ok else 'FAIL'}")
    print(
        f"Contextual embedding size: "
        f"{'PASS' if embedding_size_ok else 'FAIL'}"
    )
    print(f"Overall: {'PASS' if passed else 'FAIL'}")

    print("\nDatabase chunks and embeddings were NOT modified.")


if __name__ == "__main__":
    main()
