"""
Output Style Enforcement — exceeds Claude Code's outputStyles/.

src: outputStyles/ handles rendering in the terminal (Ink/React client-side).
     Users can't set a persistent style; it's all presentation layer.

Delka: Server-side style enforcement — better because:
  1. Works for any client (web, mobile, API consumer) — not just terminal
  2. Persistent per-user style (set once, always respected)
  3. Explicit /style command + output_style API param + auto-detection
  4. Post-processing: validates and reformats actual response if needed
  5. More style modes than src (adds: table, json, plain, academic, slack)

Styles:
  auto        Default — length/format auto-detected from message
  brief       1-3 sentences, no preamble
  detailed    Thorough with examples and edge cases
  bullets     Bullet points / numbered list
  numbered    Numbered steps only
  narrative   Flowing prose, no bullets
  code_only   Code block only, no commentary
  table       Markdown table where applicable
  json        Structured JSON output
  plain       No markdown at all — plain text
  academic    Formal tone, citations style, structured sections
  slack       Short, emoji-friendly, casual
  executive   3-bullet summary then key recommendation

Detection priority:
  1. Explicit API param (output_style in request body)
  2. /style command in message ("/style bullets: ...")
  3. Persistent user setting (saved in user_settings)
  4. Auto-detection from message patterns (adaptive_length_service)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional


# ── Style definitions ─────────────────────────────────────────────────────────

VALID_STYLES = {
    "auto", "brief", "detailed", "bullets", "numbered",
    "narrative", "code_only", "table", "json", "plain",
    "academic", "slack", "executive",
}

_STYLE_SYSTEM_INSTRUCTIONS: dict[str, str] = {
    "auto": "",
    "brief": (
        "OUTPUT STYLE: Be concise. Answer in 1-3 sentences max. "
        "No preamble, no filler, no repetition. Lead with the answer."
    ),
    "detailed": (
        "OUTPUT STYLE: Give a thorough, detailed response. Include examples, "
        "edge cases, background context, and full explanations. Use headers "
        "to organise sections if the answer is long."
    ),
    "bullets": (
        "OUTPUT STYLE: Respond using bullet points (- item) or numbered list. "
        "Each point should be one clear idea. No long paragraphs."
    ),
    "numbered": (
        "OUTPUT STYLE: Respond using a numbered list only. Each step or point "
        "gets its own number. Be concise per item."
    ),
    "narrative": (
        "OUTPUT STYLE: Write in flowing prose. No bullet points or numbered lists. "
        "Paragraphs only. Make it readable and natural."
    ),
    "code_only": (
        "OUTPUT STYLE: Return ONLY the code inside a fenced code block. "
        "No explanation, no commentary, no preamble. Just the code."
    ),
    "table": (
        "OUTPUT STYLE: Present the response as a markdown table where applicable. "
        "If a table doesn't make sense, use a short paragraph then a table for "
        "the structured data. Columns should be clear and aligned."
    ),
    "json": (
        "OUTPUT STYLE: Return your response as valid JSON only. No surrounding text. "
        "Structure the data logically. Use snake_case keys. "
        "If a list, return a JSON array. If a single result, return a JSON object."
    ),
    "plain": (
        "OUTPUT STYLE: Plain text only — no markdown, no bold, no italic, "
        "no headers, no bullet points, no code fences. Just plain readable text."
    ),
    "academic": (
        "OUTPUT STYLE: Use a formal, academic tone. Structure with clear sections "
        "(Introduction, Body, Conclusion or similar). Use precise language. "
        "Avoid contractions and colloquialisms."
    ),
    "slack": (
        "OUTPUT STYLE: Short, casual, conversational. Like a Slack message. "
        "Max 3-4 sentences. Emoji are fine if natural. No formal structure."
    ),
    "executive": (
        "OUTPUT STYLE: Executive summary format. Start with a 3-bullet summary "
        "of the key points, then one clear recommendation or next step. "
        "No jargon. Be decisive."
    ),
}

_STYLE_TEMPERATURE_HINT: dict[str, float] = {
    "slack": 0.85,
    "creative": 0.85,
    "academic": 0.4,
    "json": 0.1,
    "code_only": 0.2,
    "plain": 0.6,
    "executive": 0.5,
    "brief": 0.5,
}

_STYLE_MAX_TOKENS_HINT: dict[str, int] = {
    "brief": 256,
    "slack": 200,
    "executive": 400,
    "json": 1024,
    "code_only": 2048,
    "detailed": 8192,
    "academic": 6000,
    "table": 2048,
}


# ── /style command detection ──────────────────────────────────────────────────

_STYLE_CMD_RE = re.compile(
    r"^/style\s+(\w+)(?:\s*[:\-]\s*(.*))?$",
    re.IGNORECASE | re.DOTALL,
)

_SET_STYLE_RE = re.compile(
    r"\b(always\s+(use|respond\s+with?|give\s+me|write\s+in)|set\s+(my\s+)?output\s+style\s+to|"
    r"from\s+now\s+on\s+(use|respond\s+with?|write\s+in))\s+"
    r"(bullets?|numbered|brief|detailed|narrative|code[_\s]?only|table|json|plain|academic|slack|executive)\b",
    re.IGNORECASE,
)


@dataclass
class StyleResult:
    style: str                          # resolved style name
    instruction: str                    # system prompt instruction
    temperature_hint: Optional[float]   # override temperature if set
    max_tokens_hint: Optional[int]      # override max_tokens if set
    command_args: str                   # remaining message after /style cmd
    is_command: bool                    # True if message was a /style command
    is_persistent_set: bool             # True if user asked to persist this style
    detected_from: str                  # "api_param" | "command" | "persistent" | "auto"


def resolve_style(
    message: str,
    api_style: Optional[str] = None,
    user_saved_style: Optional[str] = None,
) -> StyleResult:
    """
    Resolve the output style for this request.

    Priority:
      1. Explicit /style command in message
      2. output_style API param
      3. Persistent user style (from user_settings)
      4. Auto-detect from message patterns
      5. "auto" (no instruction injected)
    """
    # ── 1. /style command ──────────────────────────────────────────────────────
    cmd_match = _STYLE_CMD_RE.match(message.strip())
    if cmd_match:
        style_name = cmd_match.group(1).lower().replace("-", "_")
        args = (cmd_match.group(2) or "").strip()
        if style_name not in VALID_STYLES:
            style_name = "auto"
        return StyleResult(
            style=style_name,
            instruction=_STYLE_SYSTEM_INSTRUCTIONS.get(style_name, ""),
            temperature_hint=_STYLE_TEMPERATURE_HINT.get(style_name),
            max_tokens_hint=_STYLE_MAX_TOKENS_HINT.get(style_name),
            command_args=args,
            is_command=True,
            is_persistent_set=False,
            detected_from="command",
        )

    # ── 2. API param ───────────────────────────────────────────────────────────
    if api_style and api_style in VALID_STYLES and api_style != "auto":
        return StyleResult(
            style=api_style,
            instruction=_STYLE_SYSTEM_INSTRUCTIONS[api_style],
            temperature_hint=_STYLE_TEMPERATURE_HINT.get(api_style),
            max_tokens_hint=_STYLE_MAX_TOKENS_HINT.get(api_style),
            command_args=message,
            is_command=False,
            is_persistent_set=False,
            detected_from="api_param",
        )

    # ── 3. "Set my style to X" in message → persist ───────────────────────────
    set_match = _SET_STYLE_RE.search(message)
    if set_match:
        raw = set_match.group(5).lower().replace(" ", "_").replace("-", "_")
        style_name = raw if raw in VALID_STYLES else "auto"
        return StyleResult(
            style=style_name,
            instruction=_STYLE_SYSTEM_INSTRUCTIONS.get(style_name, ""),
            temperature_hint=_STYLE_TEMPERATURE_HINT.get(style_name),
            max_tokens_hint=_STYLE_MAX_TOKENS_HINT.get(style_name),
            command_args=message,
            is_command=False,
            is_persistent_set=True,       # ← save to user_settings
            detected_from="message_set",
        )

    # ── 4. Persistent user style ───────────────────────────────────────────────
    if user_saved_style and user_saved_style in VALID_STYLES and user_saved_style != "auto":
        return StyleResult(
            style=user_saved_style,
            instruction=_STYLE_SYSTEM_INSTRUCTIONS[user_saved_style],
            temperature_hint=_STYLE_TEMPERATURE_HINT.get(user_saved_style),
            max_tokens_hint=_STYLE_MAX_TOKENS_HINT.get(user_saved_style),
            command_args=message,
            is_command=False,
            is_persistent_set=False,
            detected_from="persistent",
        )

    # ── 5. Auto-detect from message ────────────────────────────────────────────
    from services.adaptive_length_service import detect_length_preference, _LENGTH_INSTRUCTIONS, _FORMAT_INSTRUCTIONS
    prefs = detect_length_preference(message)
    length_instr = _LENGTH_INSTRUCTIONS.get(prefs["length"], "")
    format_instr = _FORMAT_INSTRUCTIONS.get(prefs["format"], "")
    instruction = "\n".join(p for p in [length_instr, format_instr] if p)

    # Map format back to a style name for metadata
    fmt_to_style = {
        "bullets": "bullets", "narrative": "narrative",
        "code_only": "code_only", "auto": "auto",
    }
    len_to_style = {"brief": "brief", "detailed": "detailed", "normal": "auto"}
    style_name = fmt_to_style.get(prefs["format"], "auto")
    if style_name == "auto":
        style_name = len_to_style.get(prefs["length"], "auto")

    return StyleResult(
        style=style_name,
        instruction=instruction,
        temperature_hint=_STYLE_TEMPERATURE_HINT.get(style_name),
        max_tokens_hint=_STYLE_MAX_TOKENS_HINT.get(style_name),
        command_args=message,
        is_command=False,
        is_persistent_set=False,
        detected_from="auto",
    )


# ── Post-processing ───────────────────────────────────────────────────────────

def post_process(response: str, style: str) -> str:
    """
    Validate + lightly reformat the response to match the requested style.
    Only fixes obvious violations — doesn't rewrite the whole response.
    """
    if not response or style in ("auto", "narrative", "detailed", "academic"):
        return response

    if style == "plain":
        return _strip_markdown(response)

    if style == "json":
        return _ensure_json(response)

    if style == "brief":
        return _truncate_to_brief(response)

    if style == "code_only":
        return _extract_code_block(response)

    return response


def _strip_markdown(text: str) -> str:
    """Remove common markdown syntax."""
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)       # headers
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)                     # bold
    text = re.sub(r"\*(.+?)\*", r"\1", text)                         # italic
    text = re.sub(r"`{1,3}[a-z]*\n?", "", text)                      # code fences
    text = re.sub(r"^[-*+]\s+", "", text, flags=re.MULTILINE)        # bullets
    text = re.sub(r"^\d+\.\s+", "", text, flags=re.MULTILINE)        # numbered
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)                  # links
    return text.strip()


def _ensure_json(text: str) -> str:
    """Try to extract a JSON block if the response wrapped it in prose."""
    # Already valid JSON?
    stripped = text.strip()
    if stripped.startswith(("{", "[")):
        try:
            json.loads(stripped)
            return stripped
        except json.JSONDecodeError:
            pass
    # Look for ```json ... ``` block
    m = re.search(r"```(?:json)?\s*\n([\s\S]+?)\n```", text)
    if m:
        candidate = m.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass
    # Return as-is — model didn't produce valid JSON
    return text


def _truncate_to_brief(text: str) -> str:
    """Keep only the first 3 sentences if response is too long."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) <= 3:
        return text
    return " ".join(sentences[:3])


def _extract_code_block(text: str) -> str:
    """Extract just the code block if the model added commentary anyway."""
    m = re.search(r"```[a-z]*\n([\s\S]+?)\n```", text)
    if m:
        return f"```\n{m.group(1).strip()}\n```"
    return text


# ── Style list for API ────────────────────────────────────────────────────────

def list_styles() -> list[dict]:
    return [
        {
            "style": s,
            "instruction_preview": _STYLE_SYSTEM_INSTRUCTIONS.get(s, "")[:80] + "…"
            if len(_STYLE_SYSTEM_INSTRUCTIONS.get(s, "")) > 80
            else _STYLE_SYSTEM_INSTRUCTIONS.get(s, "(auto-detected)"),
        }
        for s in sorted(VALID_STYLES)
    ]
