import re
from collections import Counter


# Common words that don't help identify a resource
STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then",
    "this", "that", "these", "those", "is", "are", "was",
    "were", "be", "been", "being", "to", "of", "in", "on",
    "for", "with", "from", "by", "as", "at", "it", "its",
    "into", "about", "how", "what", "when", "where", "why",
    "which", "using", "use", "used", "can", "will", "your",
    "you", "we", "our", "their", "they", "has", "have", "had"
}


def extract_keywords(
    title: str | None = None,
    description: str | None = None,
    content: str | None = None,
    max_keywords: int = 10
) -> list[str]:

    # Combine all available text
    text = " ".join(
        value
        for value in [title, description, content]
        if value
    )

    # Convert to lowercase
    text = text.lower()

    # Extract words and basic technical terms
    words = re.findall(r"[a-zA-Z0-9+#.-]+", text)

    # Remove common/unwanted words
    keywords = [
        word
        for word in words
        if (
            len(word) >= 3
            and word not in STOP_WORDS
            and not word.isdigit()
        )
    ]

    # Count keyword frequency
    word_counts = Counter(keywords)

    # Return most common keywords
    return [
        word
        for word, count in word_counts.most_common(max_keywords)
    ]


def suggest_tags(
    keywords: list[str],
    existing_tags,
    max_suggestions: int = 5
):
    keyword_set = {
        keyword.lower()
        for keyword in keywords
    }

    suggestions = []

    for tag in existing_tags:

        tag_words = set(
            tag.name.lower().split()
        )

        # Exact match for single-word tags
        if tag.name.lower() in keyword_set:
            suggestions.append({
                "id": tag.id,
                "name": tag.name
            })

        # Match multi-word tags
        elif tag_words.issubset(keyword_set):
            suggestions.append({
                "id": tag.id,
                "name": tag.name
            })

    return suggestions[:max_suggestions]