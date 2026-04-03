"""
MCP Transport Client — connects to external MCP servers and calls their tools.

Supports:
  - http   : POST {url}/tools/call  (JSON-RPC style, most common for hosted servers)
  - sse    : GET  {url}/sse         stream for server-sent events, POST for calls
  - stdio  : subprocess with stdin/stdout JSON-RPC  (local MCP servers)
  - ws     : WebSocket (future — stubs here, SSE preferred)

Protocol used: MCP JSON-RPC 2.0 (subset)
  → list tools:   {"jsonrpc":"2.0","id":1,"method":"tools/list"}
  → call tool:    {"jsonrpc":"2.0","id":2,"method":"tools/call",
                   "params":{"name":"tool_name","arguments":{...}}}

Each transport returns: {"tool": name, "result": str, "error": str|None}
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import httpx

_DEFAULT_TIMEOUT = 20   # seconds per tool call
_LIST_TIMEOUT = 10


@dataclass
class MCPToolResult:
    tool: str
    result: str = ""
    error: Optional[str] = None
    latency_ms: float = 0.0
    server: str = ""


# ── JSON-RPC helpers ──────────────────────────────────────────────────────────

def _rpc(method: str, params: dict | None = None) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4())[:8],
        "method": method,
        **({"params": params} if params else {}),
    }


def _extract_text(data: Any) -> str:
    """Pull text out of various MCP response shapes."""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        # MCP SDK: {"content": [{"type":"text","text":"..."}]}
        content = data.get("content") or data.get("result") or data.get("text") or ""
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(item.get("text") or item.get("content") or str(item))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content)
    return str(data)


# ── HTTP transport ────────────────────────────────────────────────────────────

async def _http_list_tools(url: str, headers: dict) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=_LIST_TIMEOUT, headers=headers) as client:
            resp = await client.post(url + "/tools/list", json=_rpc("tools/list"))
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", {}).get("tools", [])
    except Exception as exc:
        return [{"error": str(exc)[:200]}]


async def _http_call_tool(
    url: str, headers: dict, tool_name: str, arguments: dict
) -> MCPToolResult:
    start = time.time()
    result = MCPToolResult(tool=tool_name)
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, headers=headers) as client:
            resp = await client.post(
                url + "/tools/call",
                json=_rpc("tools/call", {"name": tool_name, "arguments": arguments}),
            )
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                result.error = str(data["error"])
            else:
                result.result = _extract_text(data.get("result", ""))
    except httpx.TimeoutException:
        result.error = f"Tool call timed out after {_DEFAULT_TIMEOUT}s"
    except Exception as exc:
        result.error = str(exc)[:200]
    result.latency_ms = round((time.time() - start) * 1000, 1)
    return result


# ── SSE transport ─────────────────────────────────────────────────────────────
# SSE servers expose tools/list via GET /sse or POST /tools/list
# Most SSE MCP servers also accept HTTP JSON-RPC on the same base URL

async def _sse_list_tools(url: str, headers: dict) -> list[dict]:
    # Try HTTP JSON-RPC first (most SSE servers support both)
    tools = await _http_list_tools(url, headers)
    if tools and "error" not in tools[0]:
        return tools
    # Fallback: GET /tools with Accept: application/json
    try:
        async with httpx.AsyncClient(timeout=_LIST_TIMEOUT, headers=headers) as client:
            resp = await client.get(url + "/tools", headers={"Accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()
            return data.get("tools", []) if isinstance(data, dict) else data
    except Exception as exc:
        return [{"error": str(exc)[:200]}]


async def _sse_call_tool(url: str, headers: dict, tool_name: str, arguments: dict) -> MCPToolResult:
    # SSE servers accept tool calls via HTTP POST (same protocol)
    return await _http_call_tool(url, headers, tool_name, arguments)


# ── Stdio transport ───────────────────────────────────────────────────────────

async def _stdio_rpc(proc: asyncio.subprocess.Process, payload: dict) -> dict:
    """Write one JSON-RPC request and read one response line."""
    line = json.dumps(payload) + "\n"
    proc.stdin.write(line.encode())
    await proc.stdin.drain()
    response_line = await asyncio.wait_for(proc.stdout.readline(), timeout=_LIST_TIMEOUT)
    return json.loads(response_line.decode().strip())


async def _stdio_list_tools(command: str, args: list[str], env: dict) -> list[dict]:
    try:
        import os
        full_env = {**os.environ, **env}
        proc = await asyncio.create_subprocess_exec(
            command, *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=full_env,
        )
        data = await _stdio_rpc(proc, _rpc("tools/list"))
        proc.stdin.close()
        await proc.wait()
        return data.get("result", {}).get("tools", [])
    except Exception as exc:
        return [{"error": str(exc)[:200]}]


async def _stdio_call_tool(
    command: str, args: list[str], env: dict, tool_name: str, arguments: dict
) -> MCPToolResult:
    start = time.time()
    result = MCPToolResult(tool=tool_name)
    try:
        import os
        full_env = {**os.environ, **env}
        proc = await asyncio.create_subprocess_exec(
            command, *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=full_env,
        )
        data = await asyncio.wait_for(
            _stdio_rpc(proc, _rpc("tools/call", {"name": tool_name, "arguments": arguments})),
            timeout=_DEFAULT_TIMEOUT,
        )
        proc.stdin.close()
        await proc.wait()
        if "error" in data:
            result.error = str(data["error"])
        else:
            result.result = _extract_text(data.get("result", ""))
    except asyncio.TimeoutError:
        result.error = f"Stdio tool call timed out after {_DEFAULT_TIMEOUT}s"
    except Exception as exc:
        result.error = str(exc)[:200]
    result.latency_ms = round((time.time() - start) * 1000, 1)
    return result


# ── Public dispatch ───────────────────────────────────────────────────────────

def _build_headers(auth_token: str | None, extra_headers: dict | None) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    if extra_headers:
        headers.update(extra_headers)
    return headers


async def list_tools(server: dict) -> list[dict]:
    """
    Fetch the tool list from an MCP server config dict.
    server keys: transport, url, auth_token, headers_json, command, args_json, env_json
    """
    transport = server.get("transport", "http")
    headers = _build_headers(
        server.get("auth_token"),
        json.loads(server["headers_json"]) if server.get("headers_json") else None,
    )

    if transport in ("http", "sse"):
        fn = _http_list_tools if transport == "http" else _sse_list_tools
        return await fn(server["url"].rstrip("/"), headers)

    elif transport == "stdio":
        args = json.loads(server["args_json"]) if server.get("args_json") else []
        env = json.loads(server["env_json"]) if server.get("env_json") else {}
        return await _stdio_list_tools(server["command"], args, env)

    return [{"error": f"Transport '{transport}' not yet supported"}]


async def call_tool(server: dict, tool_name: str, arguments: dict) -> MCPToolResult:
    """Call a tool on an external MCP server."""
    transport = server.get("transport", "http")
    headers = _build_headers(
        server.get("auth_token"),
        json.loads(server["headers_json"]) if server.get("headers_json") else None,
    )
    result = MCPToolResult(tool=tool_name, server=server.get("name", ""))

    if transport == "http":
        result = await _http_call_tool(server["url"].rstrip("/"), headers, tool_name, arguments)
    elif transport == "sse":
        result = await _sse_call_tool(server["url"].rstrip("/"), headers, tool_name, arguments)
    elif transport == "stdio":
        args = json.loads(server["args_json"]) if server.get("args_json") else []
        env = json.loads(server["env_json"]) if server.get("env_json") else {}
        result = await _stdio_call_tool(server["command"], args, env, tool_name, arguments)
    else:
        result.error = f"Transport '{transport}' not supported"

    result.server = server.get("name", "")
    return result
