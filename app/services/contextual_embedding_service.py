
import re


EXPERIMENT_RE = re.compile(
    r"^\s*Experiment\s+\d+\s*:", re.IGNORECASE
)
SUBEXPERIMENT_RE = re.compile(
    r"^\s*\d+\s*\([a-z]\)\s+\S", re.IGNORECASE
)
SECTION_RE = re.compile(
    r"^\s*(Aim|Objective|Theory|Components|Apparatus|"
    r"Circuit connections|Procedure|Program|Code|"
    r"Expected output|Sample output|Observation|"
    r"Result|Conclusion|Notes?)\s*:?(?:\s|$)",
    re.IGNORECASE,
)


def build_contextual_chunks(
    text: str,
    chunks: list[str],
    max_chars: int = 1000,
) -> list[dict[str, str]]:
    """Add document context for embedding without changing chunk content."""

    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    source_lines = []
    position = 0

    for line in normalized_text.splitlines(keepends=True):
        source_lines.append((position, line))
        position += len(line)

    results = []
    chunk_start = 0
    line_index = 0

    experiment = None
    subexperiment = None
    section = None

    for chunk in chunks:
        while (
            line_index < len(source_lines)
            and source_lines[line_index][0] <= chunk_start
        ):
            _, line = source_lines[line_index]
            stripped = line.strip()

            if EXPERIMENT_RE.match(line):
                experiment = stripped
                subexperiment = None
                section = None

            elif SUBEXPERIMENT_RE.match(line):
                subexperiment = stripped
                section = None

            else:
                match = SECTION_RE.match(line)
                if match:
                    section = match.group(1).title()

            line_index += 1

        parts = [
            part
            for part in (experiment, subexperiment)
            if part
        ]

        section_suffix = f" | Section: {section}" if section else ""
        context = " | ".join(parts) + section_suffix

        # Keep the section label when possible, shortening the title first.
        available = max_chars - len(chunk) - 1

        if len(context) > available:
            base = " | ".join(parts)
            suffix = section_suffix

            if len(suffix) > available:
                context = context[:max(0, available)]
            else:
                base_budget = available - len(suffix)

                if len(base) > base_budget:
                    if base_budget >= 4:
                        base = base[:base_budget - 3].rstrip() + "..."
                    else:
                        base = ""

                context = base + suffix

        embedding_text = (
            f"{context}\n{chunk}" if context else chunk
        )

        results.append({
            "content": chunk,
            "context": context,
            "embedding_text": embedding_text,
        })

        chunk_start += len(chunk)

    return results
