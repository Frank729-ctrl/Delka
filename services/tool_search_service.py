"""
Tool Search — ports Claude Code's ToolSearchTool, but always-on.

src: ToolSearchTool is a deferred tool Claude must explicitly invoke.
     It only returns tool names, not descriptions or usage hints.
     Only available when Claude Code is connected.

Delka: Always-on, two modes:
  1. Passive inject — when message pattern suggests tool discovery, inject
     a compact tool manifest into the system prompt so the AI knows what
     it can call without needing a separate round-trip.

  2. Active search — fuzzy keyword search across the live tool registry
     (built-in + external MCP servers) with ranked results.
     Exposed as:
       - GET /v1/mcp/tools/search?q=weather&platform=x  (API)
       - /tools [query] slash command in chat

Detection patterns:
  "what can you do", "what tools do you have", "show me your capabilities",
  "can you search", "do you have access to", "what commands", "help me with",
  "is there a tool for", "how do I use", "/tools"

Why this beats src:
  - Always-on: no deferred invocation needed
  - Descriptions + usage hints injected (src returns names only)
  - Fuzzy keyword search across all tiers (built-in + external)
  - Works mid-conversation without extra round-trip
  - Slash command /tools [query] for users to discover directly
"""
from __future__ import annotations

import re
from typing import Optional

# ── Detection ─────────────────────────────────────────────────────────────────

_TOOL_QUERY_RE = re.compile(
    r"""
    \b(
        what\s+(can\s+you\s+do|tools?\s+(do\s+you\s+have|are\s+available)|commands?\s+(do\s+you\s+have|can\s+I\s+use)|capabilities?\s+(do\s+you\s+have|are\s+available))
      | show\s+me\s+(your\s+)?(tools?|capabilities?|commands?|features?|skills?)
      | (list|show)\s+(all\s+)?(tools?|commands?|capabilities?|skills?|what\s+you\s+can)
      | do\s+you\s+have\s+(a\s+tool|access\s+to|the\s+ability)
      | (is\s+there|are\s+there)\s+a?\s*tool\s+for
      | how\s+do\s+I\s+(use|run|call|trigger|invoke)\s+(the\s+)?(\w+\s+)?tool
      | what\s+skills?\s+(do\s+you\s+have|are\s+available|can\s+I\s+use)
      | can\s+you\s+(search|calculate|translate|generate|run|execute|fetch|read|write|find)
      | help\s+me\s+understand\s+what\s+you\s+can
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def needs_tool_search(message: str) -> bool:
    """Return True if the message is asking about available tools/capabilities."""
    return bool(_TOOL_QUERY_RE.search(message))


# ── Fuzzy search ──────────────────────────────────────────────────────────────

def _score(tool: dict, query_words: list[str]) -> int:
    """Simple relevance score: count query word hits in name + description."""
    text = (tool.get("name", "") + " " + tool.get("description", "")).lower()
    return sum(text.count(w.lower()) for w in query_words)


def search_tools(tools: list[dict], query: str, max_results: int = 10) -> list[dict]:
    """
    Fuzzy keyword search over a list of tool dicts.
    Returns ranked results with name, description, source.
    """
    if not query.strip():
        return tools[:max_results]

    words = query.lower().split()
    scored = [(t, _score(t, words)) for t in tools]
    scored = [(t, s) for t, s in scored if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in scored[:max_results]]


# ── Compact manifest builder ──────────────────────────────────────────────────

def build_tool_manifest(
    tools: list[dict],
    query: Optional[str] = None,
    max_tools: int = 20,
) -> str:
    """
    Build a compact tool manifest string for injection into the system prompt.
    If query is provided, only include matching tools.
    """
    if query:
        display_tools = search_tools(tools, query, max_results=max_tools)
    else:
        display_tools = tools[:max_tools]

    if not display_tools:
        return ""

    lines = ["**Available tools** (you can call these via the agentic loop or suggest them to the user):"]
    for t in display_tools:
        name = t.get("name", "")
        desc = t.get("description", "")
        source = t.get("source", "builtin")
        source_tag = f" [{source}]" if source != "builtin" else ""
        lines.append(f"- `{name}`{source_tag}: {desc}")

    return "\n".join(lines)


def build_tool_search_response(
    tools: list[dict],
    query: str = "",
) -> str:
    """
    Build a user-facing response for the /tools slash command.
    Groups tools by source tier.
    """
    filtered = search_tools(tools, query) if query else tools

    builtin = [t for t in filtered if t.get("source", "builtin") == "builtin"]
    external = [t for t in filtered if t.get("source", "builtin") != "builtin"]

    lines = []

    if query:
        lines.append(f"**Tool search results for \"{query}\"** ({len(filtered)} found)\n")
    else:
        lines.append(f"**All available tools** ({len(filtered)} total)\n")

    if builtin:
        lines.append("**Built-in tools** (always available):")
        for t in builtin:
            desc = t.get("description", "")
            schema = t.get("input_schema", {})
            required = schema.get("required", [])
            params = ", ".join(f"`{p}`" for p in required) if required else "no params"
            lines.append(f"- `{t['name']}` ({params}) — {desc}")

    if external:
        lines.append("\n**External MCP tools**:")
        for t in external:
            source = t.get("source", "")
            lines.append(f"- `{t['name']}` [{source}] — {t.get('description', '')}")

    if not filtered:
        lines.append(f"No tools found matching \"{query}\". Try `/tools` to see all.")

    lines.append(
        "\n_Tip: These tools are called automatically when relevant. "
        "You can also ask me directly: \"search for X\", \"calculate Y\", \"run this code\"._"
    )

    return "\n".join(lines)
