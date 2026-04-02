"""
Reranking service — uses NVIDIA nv-rerankqa to reorder search results
by relevance to the query. Falls back to returning results as-is.
"""
import httpx
from config import settings


async def rerank(query: str, documents: list[str], top_n: int = 5) -> list[dict]:
    """
    Returns list of {"index": int, "text": str, "score": float} sorted by score desc.
    """
    if not documents:
        return []

    # Try NVIDIA reranker
    if settings.NVIDIA_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{settings.NVIDIA_BASE_URL}/ranking",
                    headers={
                        "Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.NVIDIA_RERANK_MODEL,
                        "query": {"text": query},
                        "passages": [{"text": doc} for doc in documents],
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    rankings = data.get("rankings", [])
                    results = []
                    for r in rankings[:top_n]:
                        idx = r.get("index", 0)
                        results.append({
                            "index": idx,
                            "text": documents[idx] if idx < len(documents) else "",
                            "score": r.get("logit", 0.0),
                        })
                    return results
        except Exception:
            pass

    # Fallback — return as-is with equal scores
    return [
        {"index": i, "text": doc, "score": 1.0 / (i + 1)}
        for i, doc in enumerate(documents[:top_n])
    ]
