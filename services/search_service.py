"""
Tavily real-time web search service.

Public API
----------
needs_search(message)          -> bool   (should we trigger a search?)
extract_search_query(message)  -> str    (clean query to send to Tavily)
search(query)                  -> str    (formatted context block, or "")
format_search_results(data)    -> str    (internal helper, exposed for tests)
"""

import re
import httpx
from utils.logger import request_logger

# ---------------------------------------------------------------------------
# Heuristic trigger
# ---------------------------------------------------------------------------

_SEARCH_TRIGGERS = re.compile(
    r"\b("
    r"what is|what are|who is|who are|where is|where are"
    r"|how (do|does|did|can|to)"
    r"|when (is|was|did|does|will)"
    r"|why (is|was|does|did)"
    r"|latest|recent|current|today|now|news|update"
    r"|price|cost|rate|score|result|winner"
    r"|define|meaning of|explain"
    r"|tell me about|search for|look up|find out"
    r")\b",
    re.IGNORECASE,
)

_QUESTION_RE = re.compile(r"\?")

# Phrases that clearly don't need a search (personal / platform-specific)
_NO_SEARCH_PHRASES = re.compile(
    r"\b("
    r"my (cv|resume|cover letter|application|background|experience)"
    r"|help me (write|create|build|improve|edit)"
    r"|review (my|this)"
    r"|delka(ai)?"
    r")\b",
    re.IGNORECASE,
)


def needs_search(message: str) -> bool:
    """Return True if the message looks like an information-retrieval query."""
    if _NO_SEARCH_PHRASES.search(message):
        return False
    if _SEARCH_TRIGGERS.search(message):
        return True
    if _QUESTION_RE.search(message) and len(message.split()) >= 4:
        return True
    return False


# ---------------------------------------------------------------------------
# Query extraction
# ---------------------------------------------------------------------------

_STRIP_LEAD = re.compile(
    r"^(can you |please |could you |do you know |i want to know |tell me )?(search for |look up |find out |what is |who is )?",
    re.IGNORECASE,
)


def extract_search_query(message: str) -> str:
    """Strip conversational preamble and return a clean search query."""
    q = message.strip().rstrip("?").strip()
    q = _STRIP_LEAD.sub("", q).strip()
    # Collapse whitespace
    q = re.sub(r"\s+", " ", q)
    return q or message.strip()


# ---------------------------------------------------------------------------
# Tavily call
# ---------------------------------------------------------------------------

_TAVILY_URL = "https://api.tavily.com/search"


async def search(query: str) -> str:
    """
    Call Tavily and return a formatted context block.
    Returns "" on error or when search is disabled/unconfigured.
    """
    from config import settings

    if not settings.SEARCH_ENABLED:
        return ""
    if not settings.TAVILY_API_KEY:
        return ""

    payload = {
        "api_key": settings.TAVILY_API_KEY,
        "query": query,
        "search_depth": settings.TAVILY_SEARCH_DEPTH,
        "max_results": settings.TAVILY_MAX_RESULTS,
        "include_answer": True,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(_TAVILY_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return format_search_results(data)
    except Exception as exc:
        request_logger.warning(f"search_service: Tavily error — {exc}")
        return ""


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------

def format_search_results(data: dict) -> str:
    """Convert Tavily response JSON into a system-prompt context block."""
    lines: list[str] = [
        "--- WEB SEARCH RESULTS ---",
        f"Query: {data.get('query', '')}",
        "",
    ]

    answer = data.get("answer", "").strip()
    if answer:
        lines.append(f"Summary: {answer}")
        lines.append("")

    results: list[dict] = data.get("results", [])
    for i, r in enumerate(results[:5], 1):
        title = r.get("title", "").strip()
        url = r.get("url", "").strip()
        content = r.get("content", "").strip()
        # Truncate long snippets
        if len(content) > 300:
            content = content[:300].rsplit(" ", 1)[0] + "…"
        lines.append(f"[{i}] {title}")
        if url:
            lines.append(f"    Source: {url}")
        if content:
            lines.append(f"    {content}")
        lines.append("")

    lines.append("--- END WEB SEARCH RESULTS ---")
    lines.append(
        "Use the above search results to answer the user's question accurately. "
        "Cite sources naturally (e.g., 'According to [title]…') when helpful."
    )
    return "\n".join(lines)
