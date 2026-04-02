"""
YouTube plugin — search for videos/songs via YouTube Data API v3.
Requires YOUTUBE_API_KEY in .env (free: 10,000 units/day).
"""
import re
import httpx

_TRIGGER = re.compile(
    r"\b("
    r"(search|find|look up|show|play|suggest).{0,30}(youtube|video|song|music|track|album|mv)"
    r"|youtube.{0,20}(search|find|video|song)"
    r"|(watch|listen to).{0,20}on youtube"
    r"|music video (for|of|by)"
    r"|songs? (by|from|of) \w+"
    r"|recommend (songs?|music|tracks?)"
    r")\b",
    re.IGNORECASE,
)


def needs_youtube(message: str) -> bool:
    from config import settings
    if not getattr(settings, "YOUTUBE_API_KEY", ""):
        return False
    return bool(_TRIGGER.search(message))


def _build_query(message: str) -> str:
    # Strip common preamble
    q = re.sub(
        r"^(can you |please |could you )?(search|find|look up|show me|play|suggest)?\s*(some\s*)?",
        "", message.strip(), flags=re.IGNORECASE
    )
    q = re.sub(r"\s*(on youtube|for me|please)\s*$", "", q, flags=re.IGNORECASE)
    return q.strip() or message.strip()


async def run_youtube(message: str) -> str:
    from config import settings
    api_key = getattr(settings, "YOUTUBE_API_KEY", "")
    if not api_key:
        return ""

    query = _build_query(message)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "maxResults": 5,
                    "key": api_key,
                },
            )
            r.raise_for_status()
            data = r.json()

        items = data.get("items", [])
        if not items:
            return ""

        lines = [f"--- YOUTUBE RESULTS: {query} ---"]
        for item in items:
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId", "")
            title    = snippet.get("title", "")
            channel  = snippet.get("channelTitle", "")
            if video_id and title:
                lines.append(f"• {title} — {channel}")
                lines.append(f"  https://www.youtube.com/watch?v={video_id}")
        lines.append("--- END ---")
        return "\n".join(lines)
    except Exception:
        return ""
