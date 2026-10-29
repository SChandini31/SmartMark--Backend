
from app.services.youtube_service import (
    extract_video_id,
    extract_video_transcript,
)

url = "https://www.youtube.com/watch?v=bm0OyhwFDuY&list=PLsyeobzWxl7pe_IiTfNyr55kwJPWbgxB5"

# Test 1: Extract the video ID
video_id = extract_video_id(url)
print("Video ID:", video_id)

# Test 2: Retrieve the transcript
try:
    result = extract_video_transcript(url)

    print("Extraction status:", result["extraction_status"])
    print("Transcript length:", len(result["extracted_text"]))
    print("Transcript preview:", result["extracted_text"][:500])

except (ValueError, RuntimeError) as exc:
    print("Transcript unavailable:", exc)
