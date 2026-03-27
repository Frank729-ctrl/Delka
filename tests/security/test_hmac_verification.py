import json
import time
import hmac as _hmac
from hashlib import sha256
import pytest
from tests.conftest import VALID_CV_PAYLOAD, make_hmac_headers


async def test_key_without_hmac_requirement_skips_check(client, valid_sk_key, mock_ollama, mock_export):
    """SK key with requires_hmac=False must NOT need HMAC headers."""
    resp = await client.post(
        "/v1/cv/generate",
        json=VALID_CV_PAYLOAD,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 200


async def test_hmac_key_without_headers_returns_401(client, valid_hmac_key):
    raw_key, _ = valid_hmac_key
    body = json.dumps(VALID_CV_PAYLOAD).encode()
    resp = await client.post(
        "/v1/cv/generate",
        content=body,
        headers={
            "X-DelkaAI-Key": raw_key,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 401


async def test_valid_hmac_signature_passes(client, valid_hmac_key, mock_ollama, mock_export):
    raw_key, hmac_secret = valid_hmac_key
    body = json.dumps(VALID_CV_PAYLOAD).encode()
    headers = make_hmac_headers(raw_key, body, hmac_secret)
    headers["Content-Type"] = "application/json"

    resp = await client.post("/v1/cv/generate", content=body, headers=headers)
    assert resp.status_code == 200


async def test_wrong_hmac_signature_returns_401(client, valid_hmac_key):
    raw_key, hmac_secret = valid_hmac_key
    body = json.dumps(VALID_CV_PAYLOAD).encode()
    ts = str(int(time.time()))

    resp = await client.post(
        "/v1/cv/generate",
        content=body,
        headers={
            "X-DelkaAI-Key": raw_key,
            "X-DelkaAI-Timestamp": ts,
            "X-DelkaAI-Signature": "badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadb",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 401


async def test_expired_timestamp_returns_401(client, valid_hmac_key):
    raw_key, hmac_secret = valid_hmac_key
    body = json.dumps(VALID_CV_PAYLOAD).encode()
    old_ts = str(int(time.time()) - 400)
    body_str = body.decode()
    message = f"{old_ts}.{body_str}"
    sig = _hmac.new(hmac_secret.encode(), message.encode(), sha256).hexdigest()

    resp = await client.post(
        "/v1/cv/generate",
        content=body,
        headers={
            "X-DelkaAI-Key": raw_key,
            "X-DelkaAI-Timestamp": old_ts,
            "X-DelkaAI-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 401


async def test_missing_timestamp_header_returns_401(client, valid_hmac_key):
    raw_key, hmac_secret = valid_hmac_key
    body = json.dumps(VALID_CV_PAYLOAD).encode()

    resp = await client.post(
        "/v1/cv/generate",
        content=body,
        headers={
            "X-DelkaAI-Key": raw_key,
            "X-DelkaAI-Signature": "somesig",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 401
