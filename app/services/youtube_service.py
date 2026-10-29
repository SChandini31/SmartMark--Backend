
import re
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi


def extract_video_id(url: str) -> str:
    """Extract a YouTube video ID from supported URL formats."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith("/embed/"):
            video_id = parsed.path.split("/")[2]
        elif parsed.path.startswith("/shorts/"):
            video_id = parsed.path.split("/")[2]
        else:
            video_id = None

    elif host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]

    else:
        video_id = None

    if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Please provide a valid YouTube video URL.")

    return video_id


def extract_video_transcript(url: str) -> dict:
    """Retrieve an available transcript for a YouTube video."""
    video_id = extract_video_id(url)

    try:
        transcript = YouTubeTranscriptApi().fetch(video_id)
        transcript_text = " ".join(
            segment.text.strip()
            for segment in transcript
            if segment.text.strip()
        )

        if not transcript_text:
            raise ValueError("The video transcript is empty.")

        return {
            "video_id": video_id,
            "extracted_text": transcript_text,
            "extraction_status": "completed",
        }

    except ValueError:
        raise
    except Exception as exc:
        # Keep the original error available for server-side debugging.
        raise RuntimeError(
            "Could not retrieve the video transcript. "
            "Captions may be unavailable or access may be restricted."
        ) from exc
