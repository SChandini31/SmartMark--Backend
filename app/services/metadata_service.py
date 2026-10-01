import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse


async def extract_metadata(url: str):
    """
    Fetch a webpage and extract basic metadata.
    """

    metadata = {
        "title": None,
        "description": None,
        "preview_image": None,
        "source_domain": None
    }

    # Extract domain from URL
    parsed_url = urlparse(url)
    metadata["source_domain"] = parsed_url.netloc

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=10.0,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        ) as client:

            response = await client.get(url)

            # Raise error for 4xx/5xx responses
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Title
        if soup.title:
            metadata["title"] = soup.title.get_text(strip=True)

        # Description
        description_tag = soup.find(
            "meta",
            attrs={"name": "description"}
        )

        if description_tag:
            metadata["description"] = description_tag.get(
                "content"
            )

        # Open Graph image
        og_image = soup.find(
            "meta",
            attrs={"property": "og:image"}
        )

        if og_image:
            metadata["preview_image"] = og_image.get("content")

        # Open Graph title is often better than <title>
        og_title = soup.find(
            "meta",
            attrs={"property": "og:title"}
        )

        if og_title and og_title.get("content"):
            metadata["title"] = og_title.get("content")

        # Open Graph description
        og_description = soup.find(
            "meta",
            attrs={"property": "og:description"}
        )

        if og_description and og_description.get("content"):
            metadata["description"] = og_description.get("content")

    except Exception as e:
        print(f"Metadata extraction failed: {e}")

    return metadata