
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from app.services.webpage_extraction_service import validate_public_url


MAX_RESPONSE_BYTES = 5 * 1024 * 1024
REQUEST_TIMEOUT = 10.0
MAX_REDIRECTS = 5


async def extract_metadata(url: str):
    """Fetch a public HTML webpage and extract its metadata."""

    metadata = {
        "title": None,
        "description": None,
        "preview_image": None,
        "source_domain": None,
    }

    current_url = url

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "SmartMark/1.0"},
        ) as client:
            for redirect_count in range(MAX_REDIRECTS + 1):
                # Validate every URL, including redirect destinations.
                validate_public_url(current_url)

                async with client.stream("GET", current_url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")

                        if not location:
                            raise ValueError(
                                "The webpage redirect is invalid."
                            )

                        if redirect_count == MAX_REDIRECTS:
                            raise ValueError(
                                "The webpage has too many redirects."
                            )

                        current_url = urljoin(current_url, location)
                        continue

                    response.raise_for_status()

                    content_type = response.headers.get(
                        "content-type", ""
                    ).lower()

                    if (
                        "text/html" not in content_type
                        and "application/xhtml+xml" not in content_type
                    ):
                        raise ValueError(
                            "The URL does not point to an HTML webpage."
                        )

                    content_length = response.headers.get("content-length")

                    if content_length:
                        try:
                            if int(content_length) > MAX_RESPONSE_BYTES:
                                raise ValueError(
                                    "The webpage is too large to process."
                                )
                        except ValueError as exc:
                            if str(exc) == "The webpage is too large to process.":
                                raise
                            # Ignore a malformed Content-Length header.

                    body = bytearray()

                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)

                        if len(body) > MAX_RESPONSE_BYTES:
                            raise ValueError(
                                "The webpage is too large to process."
                            )

                    html = bytes(body)
                    break
            else:
                raise ValueError("The webpage could not be fetched.")

        # Use the final URL's domain after redirects.
        metadata["source_domain"] = urlparse(current_url).netloc

        soup = BeautifulSoup(html, "html.parser")

        if soup.title:
            metadata["title"] = soup.title.get_text(strip=True)

        description_tag = soup.find(
            "meta", attrs={"name": "description"}
        )
        if description_tag:
            metadata["description"] = description_tag.get("content")

        og_image = soup.find(
            "meta", attrs={"property": "og:image"}
        )
        if og_image:
            metadata["preview_image"] = og_image.get("content")

        og_title = soup.find(
            "meta", attrs={"property": "og:title"}
        )
        if og_title and og_title.get("content"):
            metadata["title"] = og_title.get("content")

        og_description = soup.find(
            "meta", attrs={"property": "og:description"}
        )
        if og_description and og_description.get("content"):
            metadata["description"] = og_description.get("content")

    except ValueError:
        # Do not hide URL validation or content-limit failures.
        raise
    except httpx.TimeoutException as exc:
        raise ValueError("The webpage took too long to respond.") from exc
    except httpx.HTTPStatusError as exc:
        raise ValueError(
            f"The webpage returned HTTP {exc.response.status_code}."
        ) from exc
    except httpx.RequestError as exc:
        raise ValueError("The webpage could not be reached.") from exc

    return metadata
