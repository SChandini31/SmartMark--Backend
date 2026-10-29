
import asyncio
import json
import re
import httpx
from bs4 import BeautifulSoup

URL = "https://roadmap.sh/datastructures-and-algorithms"

TERMS = [
    "Arrays",
    "Linked Lists",
    "Sorting",
    "Binary Trees",
    "Graphs",
    "Dynamic Programming",
    "Big O",
]



def extract_roadmap_topics(payload: str) -> list[str]:
    """Extract the known DSA roadmap section titles from its serialized payload."""
    topics = re.findall(
        r'"((?:Arrays and Strings|Linked Lists and Trees|'
        r'Sorting and Searching Algorithms|Graph Algorithms Basics|'
        r'Dynamic Programming Introduction|Hash Tables and Hashing|'
        r'Stacks and Queues|Recursion and Backtracking|'
        r'Binary Search Trees|Algorithm Complexity Analysis))"',
        payload,
    )

    # Preserve order and remove duplicates.
    return list(dict.fromkeys(topics))


async def main():
    async with httpx.AsyncClient(
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        response = await client.get(URL)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    target_script = next(
        (
            script.string or script.get_text()
            for script in soup.find_all("script")
            if "window.__reactRouterContext.streamController.enqueue"
            in (script.string or script.get_text())
        ),
        None,
    )

    if not target_script:
        print("Serialized React Router payload not found.")
        return

    match = re.search(
        r"streamController\.enqueue\((\"(?:\\.|[^\"\\])*\")\)",
        target_script,
    )

    if not match:
        print("Could not isolate the serialized payload.")
        print(target_script[:1000])
        return

    try:
        payload = json.loads(match.group(1))
        topics = extract_roadmap_topics(payload)

        print("\n--- EXTRACTED DSA TOPICS ---")
        for index, topic in enumerate(topics, start=1):
            print(f"{index}. {topic}")

        print("Topic count:", len(topics))
        print("\n--- TARGET ROADMAP RECORD ---")

        for term in [
            "datastructures-and-algorithms",
            "Arrays and Strings",
            '"nodes"',
        ]:
            start = 0
            count = 0

        while True:
            pos = payload.lower().find(term.lower(), start)
            if pos == -1:
                break

            count += 1
            print(f"\n{term!r}, occurrence {count}, position {pos}:")
            print(payload[max(0, pos - 500):pos + 1200])

            start = pos + len(term)

            # Limit output so the terminal stays manageable.
            if count >= 2:
                break

    except json.JSONDecodeError as exc:
        print("Could not decode payload:", exc)
        return

    print("Decoded payload type:", type(payload).__name__)
    print("Decoded payload length:", len(payload))
    print("\n--- ROADMAP TERM SEARCH ---")

    for term in TERMS:
        position = payload.lower().find(term.lower())
        print(f"\n{term}: position={position}")

        if position >= 0:
            print(payload[max(0, position - 180):position + 350])

    print("\n--- POSSIBLE NODE FIELDS ---")
    for term in ['"title"', '"name"', '"label"', '"nodes"', '"edges"']:
        positions = [
            m.start()
            for m in re.finditer(re.escape(term), payload, re.IGNORECASE)
        ]
        print(f"{term}: {len(positions)} occurrences")
        if positions:
            pos = positions[0]
            print(payload[max(0, pos - 100):pos + 250])

if __name__ == "__main__":
    asyncio.run(main())
