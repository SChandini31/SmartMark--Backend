
import json
import re

DSA_TOPIC_PATTERN = re.compile(
    r'"((?:Arrays and Strings|Linked Lists and Trees|'
    r'Sorting and Searching Algorithms|Graph Algorithms Basics|'
    r'Dynamic Programming Introduction|Hash Tables and Hashing|'
    r'Stacks and Queues|Recursion and Backtracking|'
    r'Binary Search Trees|Algorithm Complexity Analysis))"'
)


def extract_dsa_roadmap_topics(serialized_payload: str) -> list[str]:
    """Extract known DSA section headings from a roadmap payload."""
    if not serialized_payload:
        return []

    topics = DSA_TOPIC_PATTERN.findall(serialized_payload)
    return list(dict.fromkeys(topics))


def build_dsa_roadmap_text(serialized_payload: str) -> str:
    """Build searchable text from the extracted DSA section headings."""
    topics = extract_dsa_roadmap_topics(serialized_payload)

    if not topics:
        return ""

    return (
        "Data Structures and Algorithms Roadmap\n\n"
        "Topics covered:\n"
        + "\n".join(f"- {topic}" for topic in topics)
    )
