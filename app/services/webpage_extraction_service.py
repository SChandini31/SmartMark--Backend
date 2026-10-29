import re
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup


MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB
REQUEST_TIMEOUT = 15.0
MAX_REDIRECTS = 5


def validate_public_url(url: str) -> None:
    """Allow only HTTP(S) URLs that resolve to public IP addresses."""
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS webpages are supported.")

    if not parsed.hostname:
        raise ValueError("The webpage URL is invalid.")

    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not supported.")

    hostname = parsed.hostname.lower()

    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Local webpages cannot be fetched.")

    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            resolved = socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
            addresses = [
                ipaddress.ip_address(item[4][0])
                for item in resolved
            ]
        except socket.gaierror as exc:
            raise ValueError(
                "The webpage hostname could not be resolved."
            ) from exc

    if not addresses or any(
        not address.is_global for address in addresses
    ):
        raise ValueError(
            "Private or local network URLs cannot be fetched."
        )


def _extract_fallback_text(html: bytes) -> str:
    """Extract readable text with BeautifulSoup if Trafilatura fails."""
    soup = BeautifulSoup(html, "html.parser")

    for element in soup([
        "script",
        "style",
        "noscript",
        "svg",
        "iframe",
        "nav",
        "footer",
        "header",
        "form",
        "aside",
        "button",
        "dialog",
    ]):
        element.decompose()

    # Remove common navigation, advertising, and promotional sections.
    noisy_selectors = [
        '[role="navigation"]',
        '[aria-label*="navigation" i]',
        '[class*="sidebar" i]',
        '[id*="sidebar" i]',
        '[class*="breadcrumb" i]',
        '[class*="cookie" i]',
        '[class*="newsletter" i]',
        '[class*="advert" i]',
        '[class*="promo" i]',
    ]

    for selector in noisy_selectors:
        for element in soup.select(selector):
            element.decompose()

    main_content = (
        soup.find("article")
        or soup.find("main")
        or soup.body
        or soup
    )

    return main_content.get_text(separator=" ", strip=True)





def _extract_readable_text(html: bytes) -> str:
    """Extract readable article text while preserving paragraph boundaries."""
    decoded_html = html.decode("utf-8", errors="replace")
    soup = BeautifulSoup(decoded_html, "html.parser")

    for element in soup([
        "script", "style", "noscript", "svg", "iframe",
        "nav", "footer", "header", "form", "aside",
        "button", "dialog",
    ]):
        element.decompose()

    noisy_selectors = [
        '[role="navigation"]',
        '[aria-label*="navigation" i]',
        '[class*="sidebar" i]',
        '[id*="sidebar" i]',
        '[class*="breadcrumb" i]',
        '[class*="cookie" i]',
        '[class*="newsletter" i]',
        '[class*="advert" i]',
        '[class*="promo" i]',
        '[class*="navbar" i]',
        '[class*="menu" i]',
    ]

    for selector in noisy_selectors:
        for element in soup.select(selector):
            element.decompose()

    main_content = (
        soup.find("article")
        or soup.find(attrs={"itemprop": "articleBody"})
        or soup.find("main")
        or soup.body
        or soup
    )

    # Use the article body when this webpage provides one.
    article_content = soup.select_one(".content")
    if article_content:
        main_content = article_content

    text = trafilatura.extract(
        str(main_content),
        include_comments=False,
        include_tables=True,
        include_links=False,
        output_format="txt",
        favor_precision=True,
    )

    if not text or not text.strip():
        text = main_content.get_text(separator="\n\n", strip=True)

    if not text:
        return ""

    paragraphs = [
        " ".join(paragraph.split())
        for paragraph in text.splitlines()
        if paragraph.strip()
    ]

    return "\n\n".join(paragraphs)



def clean_extracted_text(text: str) -> str:
    """Normalize extracted text without flattening paragraphs."""
    if not text:
        return ""

    text = text.replace("\xa0", " ")

    # Normalize each line while preserving paragraph boundaries.
    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in text.splitlines()
    ]

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Add a space after sentence punctuation when one is missing.
    text = re.sub(r"([.!?])(?=[A-Z])", r"\1 ", text)

    return text.strip()

async def extract_webpage_text(url: str) -> str:
    """Fetch a public webpage and extract its readable text."""

    current_url = url
    html = None

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": "SmartMark/1.0",
            },
        ) as client:

            for redirect_count in range(MAX_REDIRECTS + 1):
                # Validate every redirect destination to reduce SSRF risk.
                validate_public_url(current_url)

                async with client.stream(
                    "GET",
                    current_url,
                ) as response:

                    if response.status_code in {
                        301, 302, 303, 307, 308
                    }:
                        if redirect_count >= MAX_REDIRECTS:
                            raise ValueError(
                                "The webpage has too many redirects."
                            )

                        location = response.headers.get("location")

                        if not location:
                            raise ValueError(
                                "The webpage redirect is invalid."
                            )

                        current_url = urljoin(current_url, location)
                        continue

                    response.raise_for_status()

                    content_type = response.headers.get(
                        "content-type", ""
                    ).lower()

                    if not (
                        "text/html" in content_type
                        or "application/xhtml+xml" in content_type
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
                            if str(exc) == (
                                "The webpage is too large to process."
                            ):
                                raise

                    body = bytearray()

                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)

                        if len(body) > MAX_RESPONSE_BYTES:
                            raise ValueError(
                                "The webpage is too large to process."
                            )

                    html = bytes(body)
                    break

            if html is None:
                raise ValueError(
                    "The webpage could not be downloaded."
                )

        text = _extract_readable_text(html)

        if not text:
            raise ValueError(
                "No readable text was found on this webpage."
            )

        return text

    except httpx.TimeoutException as exc:
        raise ValueError(
            "The webpage took too long to respond."
        ) from exc

    except httpx.HTTPStatusError as exc:
        raise ValueError(
            f"The webpage returned HTTP {exc.response.status_code}."
        ) from exc
