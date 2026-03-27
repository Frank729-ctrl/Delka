import pytest
from tests.conftest import VALID_LETTER_PAYLOAD, FIXTURE_LETTER_TEXT


async def test_valid_letter_returns_pdf(client, valid_sk_key, mock_export, monkeypatch):
    async def fake_llm(task, sys_prompt, user_prompt, **kw):
        return (FIXTURE_LETTER_TEXT, "groq", "llama-3.3-70b-versatile")

    monkeypatch.setattr("services.cover_letter_service._inference_full", fake_llm)

    resp = await client.post(
        "/v1/letter/generate",
        json=VALID_LETTER_PAYLOAD,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "x-provider-used" in resp.headers
    assert "x-model-used" in resp.headers


async def test_letter_with_webhook_returns_202(client, valid_sk_key, mock_export, monkeypatch):
    async def fake_llm(task, sys_prompt, user_prompt, **kw):
        return (FIXTURE_LETTER_TEXT, "groq", "llama-3.3-70b-versatile")

    monkeypatch.setattr("services.cover_letter_service._inference_full", fake_llm)

    payload = dict(VALID_LETTER_PAYLOAD)
    payload["webhook_url"] = "https://example.com/hook"
    resp = await client.post(
        "/v1/letter/generate",
        json=payload,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 202
    assert resp.json()["data"]["status"] == "queued"


async def test_letter_missing_field_returns_422(client, valid_sk_key):
    bad = {k: v for k, v in VALID_LETTER_PAYLOAD.items() if k != "company_name"}
    resp = await client.post(
        "/v1/letter/generate",
        json=bad,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 422


async def test_letter_no_api_key_returns_401(client):
    resp = await client.post("/v1/letter/generate", json=VALID_LETTER_PAYLOAD)
    assert resp.status_code == 401
