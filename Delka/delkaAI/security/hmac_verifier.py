import hmac
import time
from hashlib import sha256
from config import settings


def verify_request_signature(
    secret: str,
    body_bytes: bytes,
    timestamp_str: str,
    received_sig: str,
) -> bool:
    try:
        timestamp = int(timestamp_str)
    except (ValueError, TypeError):
        return False

    if abs(time.time() - timestamp) > settings.HMAC_TIMESTAMP_TOLERANCE_SECONDS:
        return False

    body_text = body_bytes.decode("utf-8", errors="replace")
    message = f"{timestamp_str}.{body_text}"
    expected = hmac.new(
        secret.encode(),
        message.encode(),
        sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, received_sig)
