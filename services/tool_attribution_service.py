"""
Tool attribution — inspired by Claude Code's toolUseSummary service.

Tracks which tools/plugins fired during a chat turn and appends a subtle
attribution footnote to the response so users know what Delka used.

Format: _Sources: 🌐 Web search · 🧮 Calculator · 📍 Weather (Accra)_

Rules (like src's toolUseSummary):
- Only shown if at least one external tool fired
- Skipped for correction ack and capability_router short-circuits
- Kept brief — one line max
"""
from dataclasses import dataclass, field


@dataclass
class ToolUsage:
    """Tracks which tools fired in a single chat turn."""
    search_fired: bool = False
    search_query: str = ""
    plugins_fired: list[str] = field(default_factory=list)
    capability_used: str = ""   # "image" | "code" | "translation" | ""
    provider_used: str = ""
    was_degraded: bool = False  # Fell back from primary provider


_PLUGIN_ICONS = {
    "calculator":    ("🧮", "Calculator"),
    "datetime":      ("🕒", "Date/Time"),
    "currency":      ("💱", "Currency rates"),
    "weather":       ("🌤", "Weather"),
    "wikipedia":     ("📖", "Wikipedia"),
    "bible":         ("✝", "Bible"),
    "youtube":       ("▶", "YouTube"),
    "news":          ("📰", "News"),
}

_CAPABILITY_ICONS = {
    "image":       ("🎨", "Image generated"),
    "code":        ("💻", "Code generated"),
    "translation": ("🌍", "Translated"),
}


def build_attribution_footnote(usage: ToolUsage) -> str:
    """
    Returns a single-line attribution footnote, or empty string if
    no external tools were used.
    """
    parts = []

    if usage.search_fired:
        label = f"Web search" + (f": _{usage.search_query[:40]}_" if usage.search_query else "")
        parts.append(f"🌐 {label}")

    for plugin_name in usage.plugins_fired:
        icon, label = _PLUGIN_ICONS.get(plugin_name, ("🔧", plugin_name.title()))
        parts.append(f"{icon} {label}")

    if usage.capability_used:
        icon, label = _CAPABILITY_ICONS.get(usage.capability_used, ("⚡", usage.capability_used))
        parts.append(f"{icon} {label}")

    if not parts:
        return ""

    attribution = " · ".join(parts)
    footnote = f"\n\n_Sources: {attribution}_"

    if usage.was_degraded and usage.provider_used:
        provider_display = {
            "groq": "Groq", "nvidia": "NVIDIA", "gemini": "Gemini",
            "cerebras": "Cerebras", "ollama": "Ollama",
        }
        name = provider_display.get(usage.provider_used, usage.provider_used)
        footnote += f" · _{name} (fallback)_"

    return footnote


def detect_plugins_from_context(plugin_context: str) -> list[str]:
    """
    Given the combined plugin context string, detect which plugins fired
    by checking for their section headers.
    """
    fired = []
    checks = {
        "calculator":  "CALCULATOR",
        "datetime":    "DATE & TIME",
        "currency":    "EXCHANGE RATES",
        "weather":     "WEATHER",
        "wikipedia":   "WIKIPEDIA",
        "bible":       "BIBLE",
        "youtube":     "YOUTUBE",
        "news":        "NEWS",
    }
    ctx_upper = plugin_context.upper()
    for plugin, marker in checks.items():
        if marker in ctx_upper:
            fired.append(plugin)
    return fired
