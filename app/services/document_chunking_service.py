
import re


EXPERIMENT_HEADING = re.compile(
    r"^\s*Experiment\s+\d+\s*:",
    re.IGNORECASE,
)

SUBEXPERIMENT_HEADING = re.compile(
    r"^\s*\d+\s*\([a-z]\)\s+\S",
    re.IGNORECASE,
)

CONTENT_HEADING = re.compile(
    r"^\s*(?:"
    r"aim|objective|theory|components|apparatus|"
    r"circuit connections|procedure|program|code|"
    r"expected output|sample output|observation|"
    r"result|conclusion|notes?"
    r")\s*:?\s*$",
    re.IGNORECASE,
)


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[str]:
    """Chunk documents by experiment, then by content section."""

    if not text or not text.strip():
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between 0 and chunk_size")

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = text.splitlines(keepends=True)

    # Level 1: group lines by experiment/sub-experiment.
    units: list[list[str]] = []
    current: list[str] = []
    pending_experiment_title: list[str] = []

    def flush_current() -> None:
        nonlocal current
        if current:
            units.append(current)
            current = []

    for line in lines:
        if EXPERIMENT_HEADING.match(line):
            flush_current()
            pending_experiment_title = [line]
            continue

        if SUBEXPERIMENT_HEADING.match(line):
            flush_current()
            current = pending_experiment_title + [line]
            pending_experiment_title = []
            continue

        if not current:
            current = pending_experiment_title
            pending_experiment_title = []

        current.append(line)

    flush_current()

    if pending_experiment_title:
        units.append(pending_experiment_title)

    # Level 2: split each unit at content headings and pack
    # adjacent sections without crossing experiment boundaries.
    chunks: list[str] = []

   
    def split_oversized_block(block: str) -> list[str]:
        """Split oversized blocks at sensible line boundaries when possible."""
        parts: list[str] = []
        remaining = block

        top_level_code = re.compile(
            r"^(?:void|int|float|bool|String|const|unsigned|struct|class)\b"
        )

        while len(remaining) > chunk_size:
            limit = chunk_size
            lines = list(re.finditer(r".*?(?:\n|$)", remaining[:limit + 1]))

            # Prefer a boundary after a complete top-level code block.
            candidates: list[int] = []
            fallback: list[int] = []

            for match in lines:
                line = match.group()
                end = match.end()

                if end <= 0 or end > limit:
                    continue

                if line.strip() == "" or line.startswith(
                    ("//", "/*", "* ")
                ):
                    fallback.append(end)

                if line.strip() == "}" and not line[:1].isspace():
                    candidates.append(end)

                if top_level_code.match(line) and end < limit:
                    fallback.append(match.start())

            # Prefer a closing top-level brace; otherwise use a line boundary.
            boundary = max(candidates) if candidates else (
                max(fallback) if fallback else 0
            )

            if boundary <= 0:
                # Hard fallback guarantees progress for unusually long lines.
                boundary = limit

            parts.append(remaining[:boundary])
            remaining = remaining[boundary:]

        if remaining:
            parts.append(remaining)

        return parts


    for unit in units:
        blocks: list[str] = []
        block_lines: list[str] = []

        for line in unit:
            if block_lines and CONTENT_HEADING.match(line):
                blocks.append("".join(block_lines))
                block_lines = []

            block_lines.append(line)

        if block_lines:
            blocks.append("".join(block_lines))

        current_chunk = ""

        for block in blocks:
            if len(block) > chunk_size:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""

                chunks.extend(split_oversized_block(block))
                continue

            if current_chunk and len(current_chunk) + len(block) > chunk_size:
                chunks.append(current_chunk)
                current_chunk = ""

            current_chunk += block

        if current_chunk:
            chunks.append(current_chunk)

    return [chunk for chunk in chunks if chunk.strip()]
