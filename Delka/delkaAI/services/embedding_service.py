import base64
import io
import numpy as np
from PIL import Image

_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        from config import settings
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
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
