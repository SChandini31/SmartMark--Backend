import re
from collections import Counter


STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then",
    "this", "that", "these", "those", "is", "are", "was",
    "were", "be", "been", "being", "to", "of", "in", "on",
    "for", "with", "from", "by", "as", "at", "it", "its",
    "into", "about", "how", "what", "when", "where", "why",
    "which", "using", "use", "used", "can", "will", "your",
    "you", "we", "our", "their", "they", "has", "have", "had",
    "get", "got", "also", "one", "two", "program", "code",
    "make", "made", "work", "works", "like", "learn", "more",
    "most", "new", "free", "best", "easy", "simple", "docx",
    "pdf", "txt", "file", "document", "assignment", "lab",
    "hod", "notes", "tutorial", "guide", "page", "website",
}

CODE_STOP_WORDS = {
    "int", "void", "return", "else", "while", "for", "switch",
    "case", "break", "continue", "const", "static", "float",
    "double", "char", "bool", "true", "false", "null", "none",
    "include", "define", "class", "struct", "public", "private",
    "import", "export", "function", "var", "let", "new", "this",
    "print", "println", "serial", "setup", "loop", "off", "on",
    "key", "output", "input", "temp", "low", "high", "pin",
    "value", "state", "data", "gnd", "vcc",
}


def normalize_text(value: str) -> str:
    """Normalize text for tag comparison."""
    return " ".join(
        re.findall(r"[a-zA-Z0-9+#]+", value.casefold())
    )


def extract_keywords(
    title: str | None = None,
    description: str | None = None,
    content: str | None = None,
    max_keywords: int = 10,
) -> list[str]:
    """
    Extract useful keywords from resource metadata.

    Title has weight 3 and description has weight 2.
    Content is accepted for backward compatibility but is not
    used for existing-tag suggestions.
    """
    text_parts = [
        (title or "", 3),
        (description or "", 2),
    ]

    word_counts = Counter()

    for text, weight in text_parts:
        words = re.findall(
            r"[a-zA-Z][a-zA-Z0-9+#.-]*",
            text.casefold(),
        )

        for word in words:
            if (
                len(word) < 3
                or word in STOP_WORDS
                or word in CODE_STOP_WORDS
                or word.isdigit()
                or re.fullmatch(
                    r"[a-z]+[._-][a-z0-9._-]+",
                    word,
                )
                or re.fullmatch(
                    r"[a-z_-]*\d+[a-z0-9_-]*",
                    word,
                )
            ):
                continue

            word_counts[word] += weight

    return [
        word
        for word, _ in word_counts.most_common(max_keywords)
    ]


def suggest_tags(
    keywords: list[str],
    existing_tags,
    max_suggestions: int = 5,
) -> dict:
    """
    Suggest only tags the user has already created.

    No new tags are created automatically.
    """
    keyword_set = {
        normalize_text(keyword)
        for keyword in keywords
        if keyword and normalize_text(keyword)
    }

    existing_matches = []

    for tag in existing_tags:
        tag_name = (tag.name or "").strip()
        normalized_name = normalize_text(tag_name)

        if not normalized_name:
            continue

        tag_words = set(normalized_name.split())

        if (
            normalized_name in keyword_set
            or (
                tag_words
                and tag_words.issubset(keyword_set)
            )
        ):
            existing_matches.append({
                "id": tag.id,
                "name": tag.name,
            })

    return {
        "existing_tag_matches": existing_matches[:max_suggestions]
    }
