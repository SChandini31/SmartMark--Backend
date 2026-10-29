
import asyncio
import httpx

from app.services.webpage_extraction_service import validate_public_url

URL = "https://roadmap.sh/datastructures-and-algorithms"


async def main():
    validate_public_url(URL)

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        response = await client.get(URL)

        print("Status:", response.status_code)
        print("Final URL:", response.url)
        print("Content-Type:", response.headers.get("content-type"))
        print("HTML length:", len(response.text))
        print("\nHTML preview:")
        print(response.text[:1500])

        for term in [
            "Data Structures",
            "Algorithms",
            "__NEXT_DATA__",
            "roadmap",
        ]:
            print(
                f"{term}:",
                term.lower() in response.text.lower(),
            )


if __name__ == "__main__":
    asyncio.run(main())
