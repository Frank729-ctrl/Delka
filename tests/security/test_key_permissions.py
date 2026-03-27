import pytest
from tests.conftest import VALID_CV_PAYLOAD, VALID_LETTER_PAYLOAD


async def test_pk_can_access_support_chat(client, valid_pk_key, mock_ollama):
    resp = await client.post(
        "/v1/support/chat",
        json={"message": "Help", "platform": "generic"},
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 200


async def test_pk_can_access_health(client, valid_pk_key):
    resp = await client.get("/v1/health")
    assert resp.status_code == 200


async def test_pk_blocked_from_cv_generate(client, valid_pk_key):
    resp = await client.post(
        "/v1/cv/generate",
        json=VALID_CV_PAYLOAD,
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 403
    assert resp.json()["message"] == "This key type cannot access this endpoint."


async def test_pk_blocked_from_letter_generate(client, valid_pk_key):
    resp = await client.post(
        "/v1/letter/generate",
        json=VALID_LETTER_PAYLOAD,
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 403


async def test_sk_can_access_cv_generate(client, valid_sk_key, mock_ollama, mock_export):
    resp = await client.post(
        "/v1/cv/generate",
        json=VALID_CV_PAYLOAD,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 200


async def test_sk_can_access_letter_generate(client, valid_sk_key, mock_export, monkeypatch):
    from tests.conftest import FIXTURE_LETTER_TEXT

    async def fake_llm(task, sys_prompt, user_prompt, **kw):
        return (FIXTURE_LETTER_TEXT, "groq", "llama-3.3-70b-versatile")

    monkeypatch.setattr("services.cover_letter_service._inference_full", fake_llm)

    resp = await client.post(
        "/v1/letter/generate",
        json=VALID_LETTER_PAYLOAD,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 200
