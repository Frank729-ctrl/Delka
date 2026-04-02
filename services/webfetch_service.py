"""
WebFetch — exceeds Claude Code's WebFetch tool.

src: Fetches a URL and returns the raw markdown/text content.
Delka: Fetches any URL, strips HTML to clean readable text, summarizes
       if too long, detects content type (article, job listing, company page,
       PDF), and injects structured context into the chat system prompt.

Auto-triggered when a user pastes a URL in chat, or explicitly asks
"read this link", "summarize this page", "what does this URL say".

Also used by: cron_service (fetch daily news), doc_qa_service (remote docs).
"""
import re
from typing import Optional


_FETCH_TRIGGERS = re.compile(
    r"\b(read|fetch|summarize|check|open|look at|visit|go to|scrape|extract from)\b.{0,40}https?://",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s\"'>]+")

# Content-type sniffers based on URL patterns
_CONTENT_HINTS = {
    r"linkedin\.com/jobs": "job_listing",
    r"linkedin\.com/in/": "linkedin_profile",
    r"github\.com": "code_repository",
    r"arxiv\.org": "research_paper",
    r"\.pdf($|\?)": "pdf_document",
    r"jobberman|joblist|indeed|glassdoor|careers\.|jobs\.": "job_listing",
    r"twitter\.com|x\.com": "social_post",
    r"youtube\.com|youtu\.be": "video",
}


def needs_fetch(message: str) -> bool:
    """Returns True if the message contains a URL and likely wants it read."""
    has_url = bool(_URL_RE.search(message))
    if not has_url:
        return False
    # If message is just a URL or has fetch-intent keywords
    stripped = message.strip()
    if stripped.startswith("http"):
        return True
    return bool(_FETCH_TRIGGERS.search(message))


def extract_url(message: str) -> Optional[str]:
    """Extract the first URL from a message."""
    match = _URL_RE.search(message)
    return match.group(0) if match else None


def _detect_content_type(url: str) -> str:
    for pattern, ctype in _CONTENT_HINTS.items():
        if re.search(pattern, url, re.IGNORECASE):
            return ctype
    return "webpage"


def _clean_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace to get readable text."""
    # Remove scripts and styles entirely
    html = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", " ", html, flags=re.IGNORECASE)
    # Remove all tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    html = html.replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")
    # Collapse whitespace
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


async def fetch_url(url: str, max_chars: int = 8000) -> dict:
    """
    Fetch a URL and return structured content dict:
    {
        "url": str,
        "content_type": str,
        "text": str,           # cleaned text, max_chars
        "title": str,
        "truncated": bool,
        "error": str | None,
    }
    """
    result = {
        "url": url,
        "content_type": _detect_content_type(url),
        "text": "",
        "title": "",
        "truncated": False,
        "error": None,
    }

    try:
        import httpx
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; DelkaAI/1.0; +https://delkaai.com)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/json,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            content_type_header = resp.headers.get("content-type", "")
            raw = resp.text

        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL)
        if title_match:
            result["title"] = _clean_html(title_match.group(1))[:150]

        # Clean content
        if "html" in content_type_header or raw.strip().startswith("<"):
            text = _clean_html(raw)
        else:
            text = raw  # JSON, plain text, etc.

        if len(text) > max_chars:
            result["text"] = text[:max_chars]
            result["truncated"] = True
        else:
            result["text"] = text

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def build_fetch_context(fetch_result: dict) -> str:
    """Format fetch result as a system prompt context block."""
    if fetch_result.get("error"):
        return f"[WebFetch] Could not load {fetch_result['url']}: {fetch_result['error']}"

    lines = [f"[WebFetch — {fetch_result['content_type']}]"]
    lines.append(f"URL: {fetch_result['url']}")
    if fetch_result.get("title"):
        lines.append(f"Title: {fetch_result['title']}")
    lines.append("")
    lines.append(fetch_result["text"])
    if fetch_result.get("truncated"):
        lines.append("\n[Content truncated at 8,000 characters]")

    return "\n".join(lines)
