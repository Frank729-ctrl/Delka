import hmac
import time
from hashlib import sha256
from security.hmac_verifier import verify_request_signature


_SECRET = "fd-delka-hm-testsecret0000000000000000000000000000"


def _make_sig(body: bytes, ts: str) -> str:
    body_str = body.decode("utf-8", errors="replace")
    msg = f"{ts}.{body_str}"
    return hmac.new(_SECRET.encode(), msg.encode(), sha256).hexdigest()


def test_valid_signature_returns_true():
    body = b'{"message": "hello"}'
    ts = str(int(time.time()))
    sig = _make_sig(body, ts)
    assert verify_request_signature(_SECRET, body, ts, sig) is True


def test_wrong_signature_returns_false():
    body = b'{"message": "hello"}'
    ts = str(int(time.time()))
    assert verify_request_signature(_SECRET, body, ts, "deadbeef" * 8) is False


def test_expired_timestamp_returns_false():
    body = b'{"message": "hello"}'
    old_ts = str(int(time.time()) - 400)  # beyond 300s tolerance
    sig = _make_sig(body, old_ts)
    assert verify_request_signature(_SECRET, body, old_ts, sig) is False


def test_future_timestamp_beyond_tolerance_returns_false():
    body = b'{}'
    future_ts = str(int(time.time()) + 400)
    sig = _make_sig(body, future_ts)
    assert verify_request_signature(_SECRET, body, future_ts, sig) is False


def test_non_integer_timestamp_returns_false():
    body = b'{}'
    assert verify_request_signature(_SECRET, body, "not-a-number", "anysig") is False


def test_empty_signature_returns_false():
    body = b'{}'
    ts = str(int(time.time()))
    assert verify_request_signature(_SECRET, body, ts, "") is False
