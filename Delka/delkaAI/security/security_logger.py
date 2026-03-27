import json
from datetime import datetime
from pathlib import Path
from utils.logger import security_logger_instance

_SECURITY_LOG_PATH = Path("logs/security.log")

_SENSITIVE_KEYS = {"raw_key", "key", "password", "secret", "token", "hash"}


def _sanitize(details: dict) -> dict:
    sanitized = {}
    for k, v in details.items():
        if k.lower() in _SENSITIVE_KEYS:
            sanitized[k] = "[REDACTED]"
        elif k == "input_preview" and isinstance(v, str):
            sanitized[k] = v[:200]
        else:
            sanitized[k] = v
    return sanitized


def log_security_event(
    severity: str,
    event_type: str,
    details: dict,
) -> None:
    safe_details = _sanitize(details)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "severity": severity.upper(),
        "event_type": event_type,
        "details": safe_details,
    }
    line = json.dumps(entry, default=str)

    level = severity.upper()
    if level == "CRITICAL":
        security_logger_instance.critical(line)
    elif level == "ERROR":
        security_logger_instance.error(line)
    elif level == "WARNING":
        security_logger_instance.warning(line)
    else:
        security_logger_instance.info(line)


def get_recent_events(n: int) -> list[dict]:
    if not _SECURITY_LOG_PATH.exists():
        return []

    events: list[dict] = []
    try:
        lines = _SECURITY_LOG_PATH.read_text(encoding="utf-8").splitlines()
        for raw_line in reversed(lines):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            # Log lines are formatted: "timestamp [LEVEL] name — {json}"
            # Extract the JSON portion after " — "
            sep = " \u2014 "
            if sep in raw_line:
                json_part = raw_line.split(sep, 1)[1]
            else:
                json_part = raw_line

            try:
                events.append(json.loads(json_part))
            except json.JSONDecodeError:
                continue

            if len(events) >= n:
                break
    except Exception:
        pass

    return events
