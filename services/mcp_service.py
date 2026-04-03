"""
MCP (Model Context Protocol) — expanded from 6 hardcoded tools to a full
three-tier registry matching Claude Code's services/mcp/ depth.

Architecture:
  Tier 1 — Built-in tools  (hardcoded, always available, no config needed)
  Tier 2 — Platform tools  (registered via API, stored in DB per platform)
  Tier 3 — External servers (admin-registered MCP servers, any transport)

Tool routing order: built-in → platform DB → external MCP servers

Key features ported from src/services/mcp/:
  - Multi-transport client (http/sse/stdio/ws) via mcp_client_service
  - Per-platform server scoping (platform='hakdel' gets different tools)
  - DB-persisted server registry with CRUD
  - Tool name normalization (strips server prefix, lowercased)
  - Graceful fallback when server unavailable
  - Agentic loop: model emits tool_calls → execute → feed results back
  - Tool result caching per session (avoids redundant calls)
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

import httpx

# ── Built-in tool definitions ─────────────────────────────────────────────────

BUILTIN_TOOLS: list[dict] = [
    {
        "name": "web_search",
        "description": "Search the web for real-time information using Tavily. Use for current events, prices, people, news.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
        "source": "builtin",
    },
    {
        "name": "calculate",
        "description": "Evaluate a mathematical expression. Use for any arithmetic, percentages, currency conversions.",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string", "description": "Math expression, e.g. '15% of 2500'"}},
            "required": ["expression"],
        },
        "source": "builtin",
    },
    {
        "name": "get_weather",
        "description": "Get current weather for a city.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name, e.g. 'Accra'"}},
            "required": ["city"],
        },
        "source": "builtin",
    },
    {
        "name": "get_exchange_rate",
        "description": "Get live currency exchange rates involving GHS or other currencies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_currency": {"type": "string", "description": "Source currency, e.g. 'USD'"},
                "to_currency": {"type": "string", "description": "Target currency, e.g. 'GHS'"},
            },
            "required": ["from_currency", "to_currency"],
        },
        "source": "builtin",
    },
    {
        "name": "lookup_bible",
        "description": "Look up a Bible verse by reference.",
        "input_schema": {
            "type": "object",
            "properties": {"reference": {"type": "string", "description": "e.g. 'John 3:16'"}},
            "required": ["reference"],
        },
        "source": "builtin",
    },
    {
        "name": "search_wikipedia",
        "description": "Get a factual summary from Wikipedia about a person, place, or concept.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "source": "builtin",
    },
    {
        "name": "read_workspace_file",
        "description": "Read a file from the user's cloud workspace by filename.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "user_id": {"type": "string"},
                "platform": {"type": "string"},
            },
            "required": ["filename", "user_id", "platform"],
        },
        "source": "builtin",
    },
    {
        "name": "run_python",
        "description": "Execute Python code in a safe sandbox and return the output.",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python code to execute"}},
            "required": ["code"],
        },
        "source": "builtin",
    },
    {
        "name": "run_bash",
        "description": "Execute a restricted shell command in a safe sandbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer", "description": "Max seconds (1-30)", "default": 15},
            },
            "required": ["command"],
        },
        "source": "builtin",
    },
    {
        "name": "glob_workspace",
        "description": "Find files in the user's workspace matching a glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "e.g. '*.py' or '**/*.md'"},
                "user_id": {"type": "string"},
                "platform": {"type": "string"},
            },
            "required": ["pattern", "user_id", "platform"],
        },
        "source": "builtin",
    },
    {
        "name": "grep_workspace",
        "description": "Search for a regex pattern across all files in the user's workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern"},
                "user_id": {"type": "string"},
                "platform": {"type": "string"},
                "glob": {"type": "string", "description": "Only search files matching this glob", "default": "*"},
            },
            "required": ["pattern", "user_id", "platform"],
        },
        "source": "builtin",
    },
]

_BUILTIN_NAMES = {t["name"] for t in BUILTIN_TOOLS}


# ── In-memory tool cache (per session) ───────────────────────────────────────

_tool_cache: dict[str, dict] = {}   # session_id → {tool_call_hash: result_str}


def _cache_key(session_id: str, tool: str, args: dict) -> str:
    return f"{session_id}:{tool}:{json.dumps(args, sort_keys=True)}"


def _get_cached(session_id: str, tool: str, args: dict) -> Optional[str]:
    return _tool_cache.get(session_id, {}).get(_cache_key(session_id, tool, args))


def _set_cached(session_id: str, tool: str, args: dict, result: str) -> None:
    if session_id not in _tool_cache:
        _tool_cache[session_id] = {}
    _tool_cache[session_id][_cache_key(session_id, tool, args)] = result


def clear_tool_cache(session_id: str) -> None:
    _tool_cache.pop(session_id, None)


# ── DB server registry ────────────────────────────────────────────────────────

async def _load_platform_servers(platform: str, db: AsyncSession) -> list[dict]:
    """Load all active MCP servers for a platform from DB."""
    try:
        result = await db.execute(
            text(
                "SELECT name, transport, url, auth_token, headers_json, "
                "command, args_json, env_json, description "
                "FROM mcp_servers WHERE platform = :pl AND is_active = 1"
            ),
            {"pl": platform},
        )
        rows = result.fetchall()
        return [
            {
                "name": r[0], "transport": r[1], "url": r[2],
                "auth_token": r[3], "headers_json": r[4],
                "command": r[5], "args_json": r[6], "env_json": r[7],
                "description": r[8],
            }
            for r in rows
        ]
    except Exception:
        return []


async def get_all_tools(
    platform: str,
    db: Optional[AsyncSession] = None,
) -> list[dict]:
    """
    Return merged tool list: built-in + external MCP servers for this platform.
    Fetches live tool manifests from each registered server.
    """
    tools = list(BUILTIN_TOOLS)

    if db is None:
        return tools

    servers = await _load_platform_servers(platform, db)
    fetch_tasks = [
        _fetch_server_tools(server) for server in servers
    ]
    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
    for server, server_tools in zip(servers, results):
        if isinstance(server_tools, Exception) or not isinstance(server_tools, list):
            continue
        for tool in server_tools:
            if isinstance(tool, dict) and "name" in tool and "error" not in tool:
                tools.append({
                    **tool,
                    "source": f"mcp:{server['name']}",
                    "_server": server,
                })
    return tools


async def _fetch_server_tools(server: dict) -> list[dict]:
    from services.mcp_client_service import list_tools
    return await list_tools(server)


# ── Tool execution ────────────────────────────────────────────────────────────

async def execute_tool(
    tool_name: str,
    tool_input: dict,
    platform: str = "",
    db: Optional[AsyncSession] = None,
    session_id: str = "",
) -> str:
    """
    Execute a tool by name. Routes to built-in or external MCP server.
    Caches results per session to avoid redundant calls.
    """
    # Check cache
    if session_id:
        cached = _get_cached(session_id, tool_name, tool_input)
        if cached is not None:
            return cached

    result = await _dispatch_tool(tool_name, tool_input, platform, db)

    if session_id:
        _set_cached(session_id, tool_name, tool_input, result)

    return result


async def _dispatch_tool(
    tool_name: str,
    tool_input: dict,
    platform: str,
    db: Optional[AsyncSession],
) -> str:
    # ── Tier 1: built-in ──────────────────────────────────────────────────────
    if tool_name in _BUILTIN_NAMES:
        return await _run_builtin(tool_name, tool_input, db)

    # ── Tier 2 + 3: external MCP servers ─────────────────────────────────────
    if db:
        servers = await _load_platform_servers(platform, db)
        for server in servers:
            # Try to call this tool on each server; first success wins
            from services.mcp_client_service import call_tool
            res = await call_tool(server, tool_name, tool_input)
            if res.error is None:
                return res.result

    return f"Tool '{tool_name}' not found. Available built-in tools: {', '.join(_BUILTIN_NAMES)}"


async def _run_builtin(tool_name: str, tool_input: dict, db) -> str:
    try:
        if tool_name == "web_search":
            from services.search_service import search
            return await search(tool_input.get("query", ""))

        elif tool_name == "calculate":
            from services.plugins.calculator import run_calculator
            return await run_calculator(tool_input.get("expression", ""))

        elif tool_name == "get_weather":
            from services.plugins.weather import run_weather
            return await run_weather(tool_input.get("city", "Accra"))

        elif tool_name == "get_exchange_rate":
            return await _get_rate(
                tool_input.get("from_currency", "USD"),
                tool_input.get("to_currency", "GHS"),
            )

        elif tool_name == "lookup_bible":
            from services.plugins.bible import run_bible
            return await run_bible(tool_input.get("reference", ""))

        elif tool_name == "search_wikipedia":
            from services.plugins.wikipedia import run_wikipedia
            return await run_wikipedia(tool_input.get("query", ""))

        elif tool_name == "read_workspace_file":
            from services.workspace_service import read_file
            content = await read_file(
                tool_input["user_id"], tool_input["platform"],
                tool_input["filename"], db,
            )
            return content or f"File '{tool_input['filename']}' not found in workspace"

        elif tool_name == "run_python":
            from services.code_sandbox_service import run_python
            res = await run_python(tool_input.get("code", ""))
            return res.stdout if not res.blocked else f"Blocked: {res.block_reason}"

        elif tool_name == "run_bash":
            from services.code_sandbox_service import run_bash
            res = await run_bash(
                tool_input.get("command", ""),
                timeout=tool_input.get("timeout", 15),
            )
            return res.stdout if not res.blocked else f"Blocked: {res.block_reason}"

        elif tool_name == "glob_workspace":
            from services.workspace_service import glob_files
            matches = await glob_files(
                tool_input["user_id"], tool_input["platform"],
                tool_input.get("pattern", "*"), db,
            )
            return "\n".join(matches) if matches else "No files matched"

        elif tool_name == "grep_workspace":
            from services.workspace_service import grep_files
            results = await grep_files(
                tool_input["user_id"], tool_input["platform"],
                tool_input.get("pattern", ""), db,
                glob_filter=tool_input.get("glob", "*"),
            )
            if not results:
                return "No matches found"
            lines = []
            for r in results[:20]:
                lines.append(f"{r['filename']}:{r['line_number']}: {r['line']}")
            return "\n".join(lines)

        else:
            return f"Unknown built-in tool: {tool_name}"

    except Exception as exc:
        return f"Tool {tool_name} error: {str(exc)[:150]}"


async def _get_rate(from_c: str, to_c: str) -> str:
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(
            "https://api.frankfurter.app/latest",
            params={"from": from_c.upper(), "to": to_c.upper()},
        )
        resp.raise_for_status()
        data = resp.json()
        rate = data["rates"].get(to_c.upper())
        return f"1 {from_c.upper()} = {rate} {to_c.upper()} (live rate)" if rate else "Rate not found"


# ── Agentic tool-use loop ─────────────────────────────────────────────────────

async def run_agentic_loop(
    messages: list[dict],
    model_task: str = "chat",
    platform: str = "",
    db: Optional[AsyncSession] = None,
    session_id: str = "",
    max_turns: int = 5,
) -> str:
    """
    Full agentic tool-use loop — ports Claude Code's tool-call cycle.

    1. Call model with tools schema
    2. If model emits tool_calls → execute each tool
    3. Append tool results as 'tool' role messages
    4. Repeat up to max_turns
    5. Return final text response
    """
    from services.providers.groq_provider import GroqProvider
    from config import settings

    tools_schema = await get_all_tools(platform, db)

    provider = GroqProvider()
    if not provider.is_available():
        from services.inference_service import generate_full_response
        sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        result, _, _ = await generate_full_response(model_task, sys_msg, user_msg)
        return result

    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    current = [m for m in messages if m["role"] != "system"]

    from services.inference_service import get_task_chain
    chain = get_task_chain(model_task)
    model = chain[0]["model"] if chain else settings.SUPPORT_PRIMARY_MODEL

    for turn in range(max_turns):
        response = await provider.generate_with_tools(
            messages=current,
            model=model,
            tools=tools_schema,
            system=system,
        )

        # If string returned — no tool calls, we're done
        if isinstance(response, str):
            return response

        # Dict with tool_calls
        if isinstance(response, dict):
            text_so_far = response.get("content", "")
            tool_calls = response.get("tool_calls", [])

            if not tool_calls:
                return text_so_far

            # Append assistant message with tool_calls
            current.append({"role": "assistant", "content": text_so_far, "tool_calls": tool_calls})

            # Execute all tool calls concurrently
            async def _exec(tc: dict) -> dict:
                name = tc.get("function", {}).get("name") or tc.get("name", "")
                raw_args = tc.get("function", {}).get("arguments") or tc.get("arguments") or "{}"
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                result = await execute_tool(name, args, platform, db, session_id)
                return {
                    "role": "tool",
                    "tool_call_id": tc.get("id", name),
                    "name": name,
                    "content": result,
                }

            tool_results = await asyncio.gather(*[_exec(tc) for tc in tool_calls])
            current.extend(tool_results)

            # Loop back to let model synthesize
            continue

        # Unexpected shape — return as-is
        return str(response)

    return "Reached maximum tool-use turns without a final response."
