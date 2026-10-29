
import asyncio
import httpx
from bs4 import BeautifulSoup

URL = "https://www.geeksforgeeks.org/blogs/introduction-quantum-computing/"

async def main():
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0"}
    ) as client:
        response = await client.get(URL)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    print("Status:", response.status_code)
    print("Final URL:", response.url)
    print("Page title:", soup.title.get_text(" ", strip=True) if soup.title else None)

    for selector in ["body", "#__next", "#root", ".article", ".content", ".content-wrapper"]:
        elements = soup.select(selector)
        print(f"\n{selector}: {len(elements)} matches")

        for element in elements[:2]:
            print("Class:", element.get("class"))
            print("Text:", element.get_text(" ", strip=True)[:350])

    print("\n--- Elements with article-related attributes ---")
    for element in soup.find_all(True):
        attrs = " ".join([
            str(element.get("id", "")),
            " ".join(element.get("class", [])),
            str(element.get("itemprop", "")),
        ])
        if any(word in attrs.lower() for word in ["article", "content", "post-body"]):
            print(element.name, attrs[:200])

if __name__ == "__main__":
    asyncio.run(main())
