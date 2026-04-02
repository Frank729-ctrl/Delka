"""
Wikipedia plugin — factual summary lookups via Wikipedia REST API (free, no key).
Fires when Tavily doesn't have good coverage of a topic.
"""
import re
import httpx

_TRIGGER = re.compile(
    r"\b("
    r"who (is|was|are|were)"
    r"|what (is|was|are|were) (a |an |the )?\w+"
    r"|history of|biography|founded|invented|discovered"
    r"|tell me about|explain what|meaning of|definition of"
    r")\b",
    re.IGNORECASE,
)

_TOPIC_RE = re.compile(
    r"(?:who is|who was|what is|what was|tell me about|history of|explain)\s+(?:a |an |the )?(.+?)[\?\.!]?$",
    re.IGNORECASE,
)


def needs_wikipedia(message: str) -> bool:
    return bool(_TRIGGER.search(message))


def _extract_topic(message: str) -> str:
    m = _TOPIC_RE.search(message.strip())
    if m:
        return m.group(1).strip()
    return message.strip()


async def run_wikipedia(message: str) -> str:
    topic = _extract_topic(message)
    if not topic or len(topic) < 2:
        return ""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            # Search for the page
            search_r = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "opensearch",
                    "search": topic,
                    "limit": 1,
                    "format": "json",
                },
            )
            search_r.raise_for_status()
            search_data = search_r.json()
            titles = search_data[1]
            if not titles:
                return ""
            title = titles[0]

            # Get summary
            summary_r = await client.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}",
            )
            summary_r.raise_for_status()
            summary_data = summary_r.json()

        extract = summary_data.get("extract", "").strip()
        if not extract:
            return ""

        # Truncate to ~400 chars
        if len(extract) > 400:
            extract = extract[:400].rsplit(".", 1)[0] + "."

        page_url = summary_data.get("content_urls", {}).get("desktop", {}).get("page", "")
        lines = [
            f"--- WIKIPEDIA: {title} ---",
            extract,
        ]
        if page_url:
            lines.append(f"Source: {page_url}")
        lines.append("--- END ---")
        return "\n".join(lines)
    except Exception:
        return ""
