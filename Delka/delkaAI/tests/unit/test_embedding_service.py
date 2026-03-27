"""Unit tests for services/embedding_service.py — mocks SentenceTransformer."""
import base64
import io
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image as PILImage


def _make_mock_model(dim: int = 512):
    """Return a mock SentenceTransformer that returns random unit vectors."""
    model = MagicMock()
    def encode_side_effect(input_, convert_to_numpy=True, **kwargs):
        vec = np.random.rand(dim).astype(np.float32)
        return vec
    model.encode.side_effect = encode_side_effect
    return model


def _blank_b64(width: int = 10, height: int = 10) -> str:
    img = PILImage.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture(autouse=True)
def reset_model():
    import services.embedding_service as emb
    original = emb._model
    emb._model = None
    yield
    emb._model = original


@pytest.fixture()
def mock_model():
    model = _make_mock_model()
    with patch("sentence_transformers.SentenceTransformer", return_value=model):
        yield model


def test_generate_image_embedding_returns_list(mock_model):
    from services import embedding_service
    img = PILImage.new("RGB", (10, 10))
    result = embedding_service.generate_image_embedding(img)
    assert isinstance(result, list)
    assert all(isinstance(v, float) for v in result)


def test_generate_text_embedding_returns_list(mock_model):
    from services import embedding_service
    result = embedding_service.generate_text_embedding("red wireless headphones")
    assert isinstance(result, list)
    assert all(isinstance(v, float) for v in result)


def test_image_and_text_embeddings_same_length(mock_model):
    from services import embedding_service
    img = PILImage.new("RGB", (10, 10))
    img_vec = embedding_service.generate_image_embedding(img)
    txt_vec = embedding_service.generate_text_embedding("headphones")
    assert len(img_vec) == len(txt_vec)


def test_combine_embeddings_respects_image_weight(mock_model):
    from services import embedding_service
    dim = 512
    img_vec = [1.0] + [0.0] * (dim - 1)
    txt_vec = [0.0] * (dim - 1) + [1.0]
    result = embedding_service.combine_embeddings(img_vec, txt_vec, image_weight=1.0)
    assert result[0] > 0.9   # image_weight=1.0 → dominated by image vector


def test_output_vectors_are_normalized(mock_model):
    from services import embedding_service
    img = PILImage.new("RGB", (10, 10))
    vec = embedding_service.generate_image_embedding(img)
    magnitude = np.linalg.norm(vec)
    assert abs(magnitude - 1.0) < 1e-5


def test_combined_vector_is_normalized(mock_model):
    from services import embedding_service
    dim = 512
    img_vec = list(np.random.rand(dim))
    txt_vec = list(np.random.rand(dim))
    result = embedding_service.combine_embeddings(img_vec, txt_vec)
    magnitude = np.linalg.norm(result)
    assert abs(magnitude - 1.0) < 1e-5


def test_image_from_base64_returns_pil_image():
    from services import embedding_service
    b64 = _blank_b64()
    img = embedding_service.image_from_base64(b64)
    assert isinstance(img, PILImage.Image)
    assert img.mode == "RGB"


def test_image_from_bytes_returns_pil_image():
    from services import embedding_service
    img_src = PILImage.new("RGB", (20, 20))
    buf = io.BytesIO()
    img_src.save(buf, format="JPEG")
    result = embedding_service.image_from_bytes(buf.getvalue())
    assert isinstance(result, PILImage.Image)
