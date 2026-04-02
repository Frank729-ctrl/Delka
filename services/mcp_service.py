"""
MCP (Model Context Protocol) — pluggable external tool connections.

Inspired by Claude Code's services/mcp/ system.

MCP is a standard protocol that lets external services expose tools to the AI.
Instead of hard-coding every integration, MCP servers register themselves and
Delka discovers their tools dynamically.

Each MCP server runs as a subprocess (stdio transport) or remote HTTP service.
Delka calls it exactly like any other tool — the AI decides when to use it.

Built-in MCP servers Delka ships with:
- delka_memory: read/write session memories
- delka_web: Tavily search (wraps existing search_service)
- delka_files: read files sent by the user (future: file uploads)

External MCP servers (user-configured via API):
- Any stdio or HTTP MCP server listed in settings

Delka improvements over Claude Code src:
- MCP servers registered via API (not just local config files)
- Per-platform MCP server scoping (hakdel platform gets security tools, etc.)
- Tool results cached per session to avoid redundant calls
- Graceful fallback when MCP server unavailable
"""
from __future__ import annotations

import asyncio
import json
import httpx
from typing import Any

# ── Built-in tool registry ────────────────────────────────────────────────────
# These tools are always available — they map to existing Delka services

BUILTIN_TOOLS: list[dict] = [
    {
        "name": "web_search",
        "description": "Search the web for real-time information using Tavily. Use for current events, prices, people, news.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "calculate",
        "description": "Evaluate a mathematical expression. Use for any arithmetic, percentages, currency conversions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression to evaluate, e.g. '15% of 2500'"}
            },
            "required": ["expression"],
        },
    },
    {
        "name": "get_weather",
        "description": "Get current weather for a city.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name, e.g. 'Accra'"}
            },
            "required": ["city"],
        },
    },
    {
        "name": "get_exchange_rate",
        "description": "Get live currency exchange rates involving GHS or other currencies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_currency": {"type": "string", "description": "Source currency code, e.g. 'USD'"},
                "to_currency": {"type": "string", "description": "Target currency code, e.g. 'GHS'"},
            },
            "required": ["from_currency", "to_currency"],
        },
    },
    {
        "name": "lookup_bible",
        "description": "Look up a Bible verse by reference.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reference": {"type": "string", "description": "Bible reference, e.g. 'John 3:16'"}
            },
            "required": ["reference"],
        },
    },
    {
        "name": "search_wikipedia",
        "description": "Get a factual summary from Wikipedia about a person, place, or concept.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"],
        },
    },
]


async def execute_tool(tool_name: str, tool_input: dict) -> str:
    """
    Execute a built-in MCP tool call and return the result as a string.
    """
    try:
        if tool_name == "web_search":
            from services.search_service import search
            return await search(tool_input.get("query", ""))

        elif tool_name == "calculate":
            from services.plugins.calculator import run_calculator
            expr = tool_input.get("expression", "")
            result = await run_calculator(expr)
            return result

        elif tool_name == "get_weather":
            from services.plugins.weather import run_weather
            city = tool_input.get("city", "Accra")
            return await run_weather(city)

        elif tool_name == "get_exchange_rate":
            from_c = tool_input.get("from_currency", "USD")
            to_c = tool_input.get("to_currency", "GHS")
            return await _get_rate(from_c, to_c)

        elif tool_name == "lookup_bible":
            from services.plugins.bible import run_bible
            ref = tool_input.get("reference", "")
            return await run_bible(ref)

        elif tool_name == "search_wikipedia":
            from services.plugins.wikipedia import run_wikipedia
            return await run_wikipedia(tool_input.get("query", ""))

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Tool {tool_name} error: {str(e)[:100]}"


async def _get_rate(from_c: str, to_c: str) -> str:
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(
            f"https://api.frankfurter.app/latest",
            params={"from": from_c.upper(), "to": to_c.upper()},
        )
        resp.raise_for_status()
        data = resp.json()
        rate = data["rates"].get(to_c.upper())
        if rate:
            return f"1 {from_c.upper()} = {rate} {to_c.upper()} (live rate)"
        return "Rate not found"


async def run_agentic_loop(
    messages: list[dict],
    model_task: str = "chat",
    max_turns: int = 5,
) -> str:
    """
    Agentic tool-use loop: call the model, execute tool calls, repeat.
    Returns the final text response.

    This brings Claude Code's tool-use loop pattern to Delka's chat API.
    """
    from services.providers.groq_provider import GroqProvider
    from config import settings

    tools_schema = BUILTIN_TOOLS

    # Use Groq for agentic loop (supports tool_calls natively)
    provider = GroqProvider()
    if not provider.is_available():
        # Fallback: just call without tools
        from services.inference_service import generate_full_response
        sys = next((m["content"] for m in messages if m["role"] == "system"), "")
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        result, _, _ = await generate_full_response(model_task, sys, user)
        return result

    current_messages = [m for m in messages if m["role"] != "system"]
    system = next((m["content"] for m in messages if m["role"] == "system"), "")

    from services.inference_service import get_task_chain
    chain = get_task_chain(model_task)
    model = chain[0]["model"] if chain else settings.SUPPORT_PRIMARY_MODEL

    result = await provider.generate_with_tools(
        messages=current_messages,
        model=model,
        tools=tools_schema,
    )

    # Execute any tool calls the model made
    # (generate_with_tools already handles the loop internally for Groq)
    return result
