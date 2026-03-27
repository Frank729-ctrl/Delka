"""Unit tests for services/feedback_service.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_store_feedback_updates_rating(test_db):
    from services.feedback_service import store_feedback, store_feedback_log
    from schemas.feedback_schema import FeedbackRequest

    await store_feedback_log(
        user_id="user_a",
        platform="test",
        session_id="sess-001",
        service="support",
        request_data={},
        response_data={},
        provider_used="groq",
        model_used="llama",
        response_ms=100,
        db=test_db,
    )
    await test_db.flush()

    req = FeedbackRequest(session_id="sess-001", service="support", rating=5)
    result = await store_feedback(req, "user_a", "test", test_db)
    assert result["stored"] is True


@pytest.mark.asyncio
async def test_store_feedback_with_correction_stores_rule(test_db):
    from services.feedback_service import store_feedback, store_feedback_log
    from schemas.feedback_schema import FeedbackRequest

    await store_feedback_log(
        user_id="user_b",
        platform="test",
        session_id="sess-002",
        service="support",
        request_data={},
        response_data={},
        provider_used="groq",
        model_used="llama",
        response_ms=80,
        db=test_db,
    )
    await test_db.flush()

    req = FeedbackRequest(
        session_id="sess-002",
        service="support",
        rating=3,
        correction="Don't use bullet points",
    )
    result = await store_feedback(req, "user_b", "test", test_db)
    assert result["correction_stored"] is True


@pytest.mark.asyncio
async def test_get_rag_examples_returns_only_rating_gte_4(test_db):
    from services.feedback_service import get_rag_examples, store_feedback_log
    from schemas.feedback_schema import FeedbackRequest
    from services.feedback_service import store_feedback

    # Log 1: rated 5
    await store_feedback_log("user_c", "test", "sess-101", "chat", {}, {"r": "great"}, "groq", "m", 100, test_db)
    await test_db.flush()
    await store_feedback(FeedbackRequest(session_id="sess-101", service="chat", rating=5), "user_c", "test", test_db)

    # Log 2: rated 2
    await store_feedback_log("user_c", "test", "sess-102", "chat", {}, {"r": "bad"}, "groq", "m", 100, test_db)
    await test_db.flush()
    await store_feedback(FeedbackRequest(session_id="sess-102", service="chat", rating=2), "user_c", "test", test_db)

    examples = await get_rag_examples("user_c", "test", "chat", test_db)
    assert all(ex["response_data"].get("r") != "bad" for ex in examples)
    assert len(examples) >= 1


@pytest.mark.asyncio
async def test_get_rag_examples_respects_limit(test_db):
    from services.feedback_service import get_rag_examples, store_feedback_log
    from schemas.feedback_schema import FeedbackRequest
    from services.feedback_service import store_feedback

    for i in range(5):
        await store_feedback_log("user_d", "test", f"sess-2{i}", "support", {}, {}, "groq", "m", 100, test_db)
        await test_db.flush()
        await store_feedback(FeedbackRequest(session_id=f"sess-2{i}", service="support", rating=5), "user_d", "test", test_db)

    examples = await get_rag_examples("user_d", "test", "support", test_db, limit=2)
    assert len(examples) <= 2


@pytest.mark.asyncio
async def test_export_training_data_formats_correctly(test_db):
    from services.feedback_service import export_training_data, store_feedback_log
    from schemas.feedback_schema import FeedbackRequest
    from services.feedback_service import store_feedback

    await store_feedback_log("user_e", "myplat", "sess-301", "cv", {"q": "cv"}, {"ans": "here"}, "groq", "m", 200, test_db)
    await test_db.flush()
    await store_feedback(FeedbackRequest(session_id="sess-301", service="cv", rating=5), "user_e", "myplat", test_db)

    rows = await export_training_data("myplat", test_db, min_rating=4)
    assert len(rows) >= 1
    assert "prompt" in rows[0]
    assert "completion" in rows[0]
    assert "rating" in rows[0]
    assert "platform" in rows[0]
