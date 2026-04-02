"""
News plugin — headlines via GNews API (free: 100 req/day).
Requires GNEWS_API_KEY in .env.
Defaults to Ghana/Africa news.
"""
import re
import httpx

_TRIGGER = re.compile(
    r"\b("
    r"(latest|recent|today'?s?|current|breaking|top)\s+(news|headlines|stories)"
    r"|what'?s?\s+(happening|going on|in the news)"
    r"|news (in|about|from|on)"
    r"|headlines? (today|now|in)"
    r")\b",
    re.IGNORECASE,
)

_COUNTRY_MAP = {
    "ghana": "gh", "nigeria": "ng", "kenya": "ke",
    "south africa": "za", "uk": "gb", "us": "us", "usa": "us",
}


def needs_news(message: str) -> bool:
    from config import settings
    if not getattr(settings, "GNEWS_API_KEY", ""):
        return False
    return bool(_TRIGGER.search(message))


def _detect_country(message: str) -> str:
    lower = message.lower()
    for name, code in _COUNTRY_MAP.items():
        if name in lower:
            return code
    return "gh"  # Default to Ghana


async def run_news(message: str) -> str:
    from config import settings
    api_key = getattr(settings, "GNEWS_API_KEY", "")
    if not api_key:
        return ""

    country = _detect_country(message)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://gnews.io/api/v4/top-headlines",
                params={
                    "token": api_key,
                    "country": country,
                    "max": 5,
                    "lang": "en",
                },
            )
            r.raise_for_status()
            data = r.json()

        articles = data.get("articles", [])
        if not articles:
            return ""

        country_label = {v: k.title() for k, v in _COUNTRY_MAP.items()}.get(country, "Ghana")
        lines = [f"--- TOP NEWS: {country_label} ---"]
        for a in articles:
            title       = a.get("title", "").strip()
            source      = a.get("source", {}).get("name", "")
            published   = a.get("publishedAt", "")[:10]
            url         = a.get("url", "")
            if title:
                lines.append(f"• {title}")
                if source:
                    lines.append(f"  {source} · {published}")
                if url:
                    lines.append(f"  {url}")
        lines.append("--- END ---")
        return "\n".join(lines)
    except Exception:
        return ""
