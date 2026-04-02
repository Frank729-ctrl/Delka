"""
Currency plugin — live exchange rates via frankfurter.app (free, no key).
Supports GHS, USD, GBP, EUR, NGN, etc.
"""
import re
import httpx

_TRIGGER = re.compile(
    r"\b("
    r"exchange rate|forex|fx rate"
    r"|dollar to (cedi|ghs|ghana)"
    r"|pound to (cedi|ghs|ghana)"
    r"|euro to (cedi|ghs|ghana)"
    r"|(cedi|cedis) (to|rate|exchange|in|is)"
    r"|(how many|how much) (cedi|cedis|ghs)"
    r"|ghs (to|rate)"
    r"|how much is (a |the )?(dollar|pound|euro|usd|gbp|eur)"
    r"|\d+\s*(dollar|pound|euro|usd|gbp|eur)s?\s+in\s+(cedi|ghs|ghana)"
    r"|convert \d"
    r"|currency (rate|converter|today)"
    r")\b",
    re.IGNORECASE,
)

# Currency codes to always fetch against GHS
_DEFAULT_BASE = "USD"
_EXTRA_CURRENCIES = ["GBP", "EUR", "NGN", "GHS"]

_CURRENCY_NAMES = {
    "USD": "US Dollar", "GBP": "British Pound", "EUR": "Euro",
    "NGN": "Nigerian Naira", "GHS": "Ghana Cedi",
}


def needs_currency(message: str) -> bool:
    return bool(_TRIGGER.search(message))


def _detect_base(message: str) -> str:
    m = message.upper()
    if "POUND" in m or "GBP" in m: return "GBP"
    if "EURO" in m or "EUR" in m:  return "EUR"
    if "NAIRA" in m or "NGN" in m: return "NGN"
    return "USD"


async def run_currency(message: str) -> str:
    base = _detect_base(message)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"https://api.frankfurter.app/latest",
                params={"from": base, "to": "GHS"},
            )
            r.raise_for_status()
            data = r.json()

        rates = data.get("rates", {})
        ghs_rate = rates.get("GHS")
        if not ghs_rate:
            return ""

        base_name = _CURRENCY_NAMES.get(base, base)
        lines = [
            f"--- LIVE EXCHANGE RATE ---",
            f"1 {base_name} ({base}) = GHS {ghs_rate:.4f}",
            f"Source: European Central Bank via frankfurter.app",
            f"--- END ---",
        ]
        return "\n".join(lines)
    except Exception:
        return ""
