
import asyncio

from app.services.webpage_extraction_service import extract_webpage_text


async def main():
    url = "https://www.geeksforgeeks.org/blogs/introduction-quantum-computing/"

    try:
        text = await extract_webpage_text(url)

        print("\n--- EXTRACTION RESULTS ---")
        print("Characters extracted:", len(text))
        print("\n--- FIRST 2000 CHARACTERS ---")
        print(text[:2000])
        print("\n--- LAST 1000 CHARACTERS ---")
        print(text[-1000:])
        keywords = [
            "quantum computing",
            "qubit",
            "superposition",
            "entanglement",
        ]

        print("\n--- KEYWORD CHECK ---")
        for keyword in keywords:
            print(f"{keyword}: {keyword.lower() in text.lower()}")

    except Exception as exc:
        print("Extraction failed:", type(exc).__name__, str(exc))


if __name__ == "__main__":
    asyncio.run(main())
