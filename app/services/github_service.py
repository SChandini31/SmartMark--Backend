
import httpx

GITHUB_API_BASE = "https://api.github.com"
REQUEST_TIMEOUT = 15.0
MAX_README_BYTES = 2 * 1024 * 1024


async def extract_github_readme(url: str) -> dict:
    """
    Extract repository metadata and README text from a public
    GitHub repository.

    Returns:
        {
            "title": repository name,
            "description": repository description,
            "source_domain": "github.com",
            "extracted_text": README text or None,
            "extraction_status": "completed" or "failed"
        }
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]

    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"github.com", "www.github.com"}
        or len(parts) < 2
        or parts[0] in {"login", "settings", "organizations"}
    ):
        raise ValueError("Please provide a valid GitHub repository URL.")

    owner, repo = parts[0], parts[1]
    repo = repo.removesuffix(".git")

    if not owner or not repo:
        raise ValueError("The GitHub repository URL is incomplete.")

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SmartMark",
    }

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers=headers,
    ) as client:
        response = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
        )

        if response.status_code == 404:
            raise ValueError(
                "GitHub repository not found or not publicly accessible."
            )

        response.raise_for_status()
        repository = response.json()

        if repository.get("private"):
            raise ValueError("Only public GitHub repositories are supported.")

        readme_response = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/readme"
        )

        readme_text = None

        if readme_response.status_code == 200:
            readme_data = readme_response.json()

            download_url = readme_data.get("download_url")
            if download_url:
                # Fetch only from GitHub's expected raw-content host.
                from urllib.parse import urlparse as parse_url

                download_host = parse_url(download_url).hostname
                if download_host not in {
                    "raw.githubusercontent.com",
                    "github.com",
                }:
                    raise ValueError("Unexpected GitHub README download host.")

                content_response = await client.get(download_url)
                content_response.raise_for_status()

                if len(content_response.content) > MAX_README_BYTES:
                    raise ValueError("The repository README is too large.")

                readme_text = content_response.text.strip()

        elif readme_response.status_code not in {404}:
            readme_response.raise_for_status()

    return {
        "title": repository.get("full_name") or f"{owner}/{repo}",
        "description": repository.get("description"),
        "source_domain": "github.com",
        "extracted_text": readme_text,
        "extraction_status": (
            "completed" if readme_text else "failed"
        ),
    }
