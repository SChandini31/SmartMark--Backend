
import asyncio
import httpx
from bs4 import BeautifulSoup

URL = "https://roadmap.sh/datastructures-and-algorithms"

async def main():
    async with httpx.AsyncClient(
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        response = await client.get(URL)
        response.raise_for_status()

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    print("PAGE TITLE:", soup.title.get_text(strip=True) if soup.title else "None")

    description = soup.find("meta", attrs={"name": "description"})
    print("DESCRIPTION:", description.get("content") if description else "None")

    print("\n--- SCRIPT TAGS ---")
    for i, script in enumerate(soup.find_all("script")):
        content = script.string or script.get_text()
        if not content:
            continue

        matches = [
            term for term in [
                "Data Structures",
                "Algorithms",
                "roadmapData",
                "nodes",
                "edges",
                "localStorage",
            ]
            if term.lower() in content.lower()
        ]

        if matches:
            print(
                f"\nScript {i}: id={script.get('id')!r}, "
                f"type={script.get('type')!r}, "
                f"length={len(content)}, matches={matches}"
            )
            print(content[:800])

    print("\n--- RAW HTML CONTEXT ---")
    for term in [
        "Step by step guide",
        "Data Structures & Algorithms",
        "roadmapData",
    ]:
        pos = html.lower().find(term.lower())
        print(f"\n{term}: position={pos}")
        if pos >= 0:
            print(html[max(0, pos - 250):pos + 700])

    print("\n--- VISIBLE TEXT PREVIEW ---")
    text = soup.get_text(" ", strip=True)
    print(text[:2500])

if __name__ == "__main__":
    asyncio.run(main())
