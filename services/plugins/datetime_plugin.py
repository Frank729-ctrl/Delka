"""
DateTime plugin — returns current date and time in Ghana (GMT/WAT).
No API needed.
"""
import re
from datetime import datetime, timezone, timedelta

_TRIGGER = re.compile(
    r"\b("
    r"what (time|day|date|year|month) is it"
    r"|what day is (it|today)"
    r"|current (time|date|day)"
    r"|today'?s? date"
    r"|what'?s? the (time|date|day)"
    r"|time (now|in ghana|right now)"
    r"|day (today|is it)"
    r")\b",
    re.IGNORECASE,
)

# Ghana is GMT+0 (no DST)
_GHANA_TZ = timezone(timedelta(hours=0))


def needs_datetime(message: str) -> bool:
    return bool(_TRIGGER.search(message))


def run_datetime(_message: str) -> str:
    now = datetime.now(_GHANA_TZ)
    day_name  = now.strftime("%A")
    date_str  = now.strftime("%d %B %Y")
    time_str  = now.strftime("%I:%M %p")
    return (
        f"--- CURRENT DATE & TIME (Ghana / GMT) ---\n"
        f"{day_name}, {date_str} — {time_str} GMT\n"
        f"--- END ---"
    )
