"""
Plugin orchestrator — runs all enabled plugins in parallel and returns
a combined context string to inject into the chat system prompt.
"""
import asyncio
import inspect

from .calculator import needs_calculator, run_calculator
from .datetime_plugin import needs_datetime, run_datetime
from .currency import needs_currency, run_currency
from .weather import needs_weather, run_weather
from .wikipedia import needs_wikipedia, run_wikipedia
from .bible import needs_bible, run_bible
from .youtube import needs_youtube, run_youtube
from .news import needs_news, run_news


async def run_plugins(message: str) -> str:
    """
    Check all plugins against the user message, run matching ones in parallel,
    and return a combined context string (empty string if no plugins fired).
    """
    tasks = []

    if needs_calculator(message):
        tasks.append(_safe(run_calculator(message)))
    if needs_datetime(message):
        tasks.append(_safe(run_datetime(message)))
    if needs_currency(message):
        tasks.append(_safe(run_currency(message)))
    if needs_weather(message):
        tasks.append(_safe(run_weather(message)))
    if needs_wikipedia(message):
        tasks.append(_safe(run_wikipedia(message)))
    if needs_bible(message):
        tasks.append(_safe(run_bible(message)))
    if needs_youtube(message):
        tasks.append(_safe(run_youtube(message)))
    if needs_news(message):
        tasks.append(_safe(run_news(message)))

    if not tasks:
        return ""

    results = await asyncio.gather(*tasks)
    parts = [r for r in results if r]
    return "\n\n".join(parts)


async def _safe(result) -> str:
    """Handle both sync plugin results and async coroutines safely."""
    try:
        if inspect.iscoroutine(result):
            result = await result
        return result or ""
    except Exception:
        return ""
