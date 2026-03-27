"""Unit tests for services/index_service.py — mocks ChromaDB."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_chroma_collection(count: int = 0):
    col = MagicMock()
    col.count.return_value = count
    col.upsert = MagicMock()
    col.query.return_value = {
        "ids": [["platform_item1", "platform_item2"]],
        "distances": [[0.1, 0.4]],
        "metadatas": [
            [
                {"item_id": "item1", "platform": "test", "name": "Product A"},
                {"item_id": "item2", "platform": "test", "name": "Product B"},
            ]
        ],
    }
    col.delete = MagicMock()
    return col


@pytest.fixture(autouse=True)
def reset_chroma_client():
    import services.index_service as svc
    original = svc._client
    svc._client = None
    yield
    svc._client = original


@pytest.fixture()
def mock_collection():
    col = _make_chroma_collection(count=5)
    with patch("services.index_service.get_chroma_client") as mock_client:
        mock_client.return_value.get_or_create_collection.return_value = col
        with patch("config.settings.CHROMA_PERSIST_DIR", "/tmp/test_chroma"):
            yield col


@pytest.mark.asyncio
async def test_get_collection_creates_with_cosine_distance():
    import chromadb
    mock_client = MagicMock()
    mock_col = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_col

    with patch("services.index_service.get_chroma_client", return_value=mock_client):
        from services.index_service import get_collection
        result = get_collection("test_platform")

    mock_client.get_or_create_collection.assert_called_once_with(
        name="test_platform_index",
        metadata={"hnsw:space": "cosine"},
    )
    assert result is mock_col


@pytest.mark.asyncio
async def test_index_single_item_calls_upsert(mock_collection):
    from services import index_service
    from unittest.mock import AsyncMock, MagicMock
    from sqlalchemy.ext.asyncio import AsyncSession

    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    db.add = MagicMock()

    embedding = [0.1] * 512
    result = await index_service.index_single_item(
        platform="test",
        item_id="item_001",
        embedding=embedding,
        metadata={"name": "Widget"},
        image_url="http://example.com/img.jpg",
        db=db,
    )
    assert result is True
    mock_collection.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_search_similar_converts_distance_to_similarity():
    from services import index_service
    col = _make_chroma_collection(count=5)
    col.query.return_value = {
        "ids": [["test_item1"]],
        "distances": [[0.1]],   # similarity = 1 - 0.1 = 0.9
        "metadatas": [[{"item_id": "item1", "platform": "test", "name": "A"}]],
    }
    with patch("services.index_service.get_chroma_client") as mock_client:
        mock_client.return_value.get_or_create_collection.return_value = col
        results = await index_service.search_similar(
            platform="test",
            query_embedding=[0.0] * 512,
            limit=10,
            min_similarity=0.0,
        )
    assert len(results) == 1
    assert abs(results[0]["similarity_score"] - 0.9) < 1e-4


@pytest.mark.asyncio
async def test_search_similar_filters_below_min_similarity():
    from services import index_service
    col = _make_chroma_collection(count=5)
    col.query.return_value = {
        "ids": [["test_item1", "test_item2"]],
        "distances": [[0.1, 0.5]],  # similarities: 0.9, 0.5
        "metadatas": [
            [
                {"item_id": "item1", "platform": "test"},
                {"item_id": "item2", "platform": "test"},
            ]
        ],
    }
    with patch("services.index_service.get_chroma_client") as mock_client:
        mock_client.return_value.get_or_create_collection.return_value = col
        results = await index_service.search_similar(
            platform="test",
            query_embedding=[0.0] * 512,
            limit=10,
            min_similarity=0.8,   # only sim=0.9 passes
        )
    assert len(results) == 1
    assert results[0]["item_id"] == "item1"


@pytest.mark.asyncio
async def test_remove_item_deletes_from_chroma_and_sql():
    from services import index_service
    from unittest.mock import AsyncMock, MagicMock
    from sqlalchemy.ext.asyncio import AsyncSession

    col = MagicMock()
    col.delete = MagicMock()
    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock()

    with patch("services.index_service.get_chroma_client") as mock_client:
        mock_client.return_value.get_or_create_collection.return_value = col
        result = await index_service.remove_item("test", "item_001", db)

    assert result is True
    col.delete.assert_called_once_with(ids=["test_item_001"])


@pytest.mark.asyncio
async def test_platform_exists_returns_false_for_empty_collection():
    from services import index_service
    col = MagicMock()
    col.count.return_value = 0
    with patch("services.index_service.get_chroma_client") as mock_client:
        mock_client.return_value.get_or_create_collection.return_value = col
        result = await index_service.platform_exists("empty_platform")
    assert result is False
