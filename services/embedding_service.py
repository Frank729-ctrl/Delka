import base64
import io
import numpy as np
from PIL import Image

# ── Cohere text embeddings (async, primary for RAG/reranking) ─────────────────

async def generate_text_embedding_cohere(text: str) -> list[float] | None:
    """
    Text embedding via Cohere embed-v4 (multilingual, 1024-d).
    Falls back to None so callers can use CLIP instead.
    """
    try:
        from config import settings
        if not settings.COHERE_API_KEY:
            return None
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.cohere.com/v2/embed",
                headers={
                    "Authorization": f"Bearer {settings.COHERE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.COHERE_EMBED_MODEL,
                    "texts": [text],
                    "input_type": "search_query",
                    "embedding_types": ["float"],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            vec = data["embeddings"]["float"][0]
            arr = np.array(vec, dtype=np.float32)
            return (arr / np.linalg.norm(arr)).tolist()
    except Exception:
        return None

_model = None


def get_model():
    global _model
    if _model is None:
        import os
        from sentence_transformers import SentenceTransformer
        from config import settings
        os.environ.setdefault("HF_HUB_OFFLINE", "0")
        try:
            _model = SentenceTransformer(settings.EMBEDDING_MODEL)
        except Exception as e:
            raise RuntimeError(
                f"CLIP model '{settings.EMBEDDING_MODEL}' could not be loaded. "
                f"Run: python -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('{settings.EMBEDDING_MODEL}')\" "
                f"to download it first. Error: {e}"
            )
    return _model


def image_from_base64(b64_string: str) -> Image.Image:
    image_bytes = base64.b64decode(b64_string)
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def image_from_bytes(raw_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(raw_bytes)).convert("RGB")


def generate_image_embedding(image: Image.Image) -> list[float]:
    model = get_model()
    embedding = model.encode(image, convert_to_numpy=True)
    normalized = embedding / np.linalg.norm(embedding)
    return normalized.tolist()


def generate_text_embedding(text: str) -> list[float]:
    model = get_model()
    embedding = model.encode(text, convert_to_numpy=True)
    normalized = embedding / np.linalg.norm(embedding)
    return normalized.tolist()


def combine_embeddings(
    image_vector: list[float],
    text_vector: list[float],
    image_weight: float = 0.7,
) -> list[float]:
    img = np.array(image_vector)
    txt = np.array(text_vector)
    combined = (image_weight * img) + ((1 - image_weight) * txt)
    normalized = combined / np.linalg.norm(combined)
    return normalized.tolist()
