import hmac
import json
from hashlib import sha256
import httpx
from config import settings
from utils.logger import request_logger


async def deliver(url: str, payload: dict, secret: str) -> bool:
    body = json.dumps(payload, default=str)
    signature = hmac.new(
        secret.encode(),
        body.encode(),
        sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-DelkaAI-Signature": signature,
    }

    for attempt in range(1, settings.WEBHOOK_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(
                timeout=settings.WEBHOOK_TIMEOUT_SECONDS
            ) as client:
                response = await client.post(url, content=body, headers=headers)
                if response.status_code < 400:
                    request_logger.info(
                        f"webhook delivered url={url} attempt={attempt} status={response.status_code}"
                    )
                    return True
                request_logger.warning(
                    f"webhook failed url={url} attempt={attempt} status={response.status_code}"
                )
        except Exception as exc:
            request_logger.warning(
                f"webhook error url={url} attempt={attempt} error={exc}"
            )

    request_logger.error(
        f"webhook exhausted retries url={url} max_retries={settings.WEBHOOK_MAX_RETRIES}"
    )
    return False
