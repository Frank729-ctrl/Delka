"""
Adaptive response length — exceeds Claude Code's BriefTool.

src: BriefTool lets users manually request shorter responses.
Delka: AUTO-detects intent from message patterns and injects length
       instructions into the system prompt dynamically.

Detection levels:
- BRIEF:   "quick", "short", "brief", "tldr", "summarize", "in a sentence"
- DETAILED: "explain in detail", "walk me through", "comprehensive", "full"
- NORMAL:  everything else

Also detects format preferences:
- BULLETS: "list", "bullet points", "steps"
- NARRATIVE: "explain", "tell me", "describe"
- CODE_ONLY: "just the code", "only show me the code"
"""
import re

_BRIEF_RE = re.compile(
    r"\b(quick(ly)?|short(ly)?|brief(ly)?|tl;?dr|in a (sentence|word|nutshell)|"
    r"summarize|summary|just tell me|simple answer|quick answer|keep it short)\b",
    re.IGNORECASE,
)

_DETAILED_RE = re.compile(
    r"\b(in detail|detailed|explain (fully|thoroughly|completely)|"
    r"walk me through|step by step|comprehensive|in depth|elaborate|"
    r"full explanation|break it down|teach me)\b",
    re.IGNORECASE,
)

_BULLETS_RE = re.compile(
    r"\b(list|bullet points?|numbered list|steps?|pros and cons|"
    r"advantages and disadvantages|compare)\b",
    re.IGNORECASE,
)

_CODE_ONLY_RE = re.compile(
    r"\b(just (the )?code|only (show|give) (me )?(the )?code|"
    r"no explanation|code only|without explanation)\b",
    re.IGNORECASE,
)

_NARRATIVE_RE = re.compile(
    r"\b(explain|tell me|describe|what is|how does|why does|"
    r"help me understand|I('m| am) confused)\b",
    re.IGNORECASE,
)


def detect_length_preference(message: str) -> dict:
    """
    Returns a dict with: length (brief|normal|detailed), format (auto|bullets|narrative|code_only)
    """
    length = "normal"
    fmt = "auto"

    if _BRIEF_RE.search(message):
        length = "brief"
    elif _DETAILED_RE.search(message):
        length = "detailed"

    if _CODE_ONLY_RE.search(message):
        fmt = "code_only"
    elif _BULLETS_RE.search(message):
        fmt = "bullets"
    elif _NARRATIVE_RE.search(message):
        fmt = "narrative"

    return {"length": length, "format": fmt}


_LENGTH_INSTRUCTIONS = {
    "brief": (
        "RESPONSE LENGTH: Be concise. Answer in 1-3 sentences max. "
        "No preamble, no explanation unless asked."
    ),
    "normal": "",
    "detailed": (
        "RESPONSE LENGTH: Give a thorough, detailed response. "
        "Include examples, edge cases, and full explanations."
    ),
}

_FORMAT_INSTRUCTIONS = {
    "auto": "",
    "bullets": "RESPONSE FORMAT: Use bullet points or numbered steps.",
    "narrative": "RESPONSE FORMAT: Write in flowing prose, not bullet points.",
    "code_only": "RESPONSE FORMAT: Return ONLY the code. No explanation, no commentary.",
}


def build_length_instruction(message: str) -> str:
    """Returns the length+format instruction to prepend to the system prompt."""
    prefs = detect_length_preference(message)
    parts = []

    length_instr = _LENGTH_INSTRUCTIONS.get(prefs["length"], "")
    if length_instr:
        parts.append(length_instr)

    format_instr = _FORMAT_INSTRUCTIONS.get(prefs["format"], "")
    if format_instr:
        parts.append(format_instr)

    return "\n".join(parts)
