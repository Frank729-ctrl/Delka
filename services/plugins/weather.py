"""
Weather plugin — real-time weather via wttr.in (free, no key).
Defaults to Accra if no city is mentioned.
"""
import re
import httpx

_TRIGGER = re.compile(
    r"\b("
    r"weather|temperature|forecast|rain(ing)?|sunny|hot|cold|humid"
    r"|how (hot|cold|warm) is it"
    r"|will it rain"
    r"|weather in|climate in"
    r")\b",
    re.IGNORECASE,
)

_CITY_RE = re.compile(
    r"\b(?:weather|forecast|temperature|rain)\s+(?:in|at|for)\s+([A-Za-z\s]{2,30})\b",
    re.IGNORECASE,
)

_GHANA_CITIES = {
    "accra", "kumasi", "tamale", "takoradi", "tema", "cape coast",
    "sunyani", "koforidua", "ho", "wa", "bolgatanga",
}


def needs_weather(message: str) -> bool:
    return bool(_TRIGGER.search(message))


def _extract_city(message: str) -> str:
    m = _CITY_RE.search(message)
    if m:
        return m.group(1).strip()
    # Default to Accra
    return "Accra"


async def run_weather(message: str) -> str:
    city = _extract_city(message)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"https://wttr.in/{city}",
                params={"format": "j1"},
                headers={"User-Agent": "DelkaAI/1.0"},
            )
            r.raise_for_status()
            data = r.json()

        current = data["current_condition"][0]
        temp_c   = current["temp_C"]
        feels_c  = current["FeelsLikeC"]
        humidity = current["humidity"]
        desc     = current["weatherDesc"][0]["value"]
        wind_kph = current["windspeedKmph"]

        # Nearest area
        area = data.get("nearest_area", [{}])[0]
        area_name = area.get("areaName", [{}])[0].get("value", city)
        country   = area.get("country", [{}])[0].get("value", "")

        lines = [
            f"--- WEATHER: {area_name}, {country} ---",
            f"Condition: {desc}",
            f"Temperature: {temp_c}°C (feels like {feels_c}°C)",
            f"Humidity: {humidity}%",
            f"Wind: {wind_kph} km/h",
            f"Source: wttr.in",
            f"--- END ---",
        ]
        return "\n".join(lines)
    except Exception:
        return ""
