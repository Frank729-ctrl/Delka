"""
Streaming Artifacts — detect and emit renderable content blocks in responses.

When Delka's response contains HTML, SVG, Mermaid diagrams, React/JSX, or
standalone code blocks, this service extracts them and emits typed SSE events
so clients can render them natively instead of displaying raw text.

Artifact types and their client rendering hints:
  html        → render in sandboxed iframe
  svg         → render as inline SVG
  mermaid     → render with mermaid.js
  react       → render with React runtime
  code        → syntax-highlighted code block (language tagged)
  json        → formatted JSON viewer
  table       → render as HTML table (from markdown table)
  math        → render with KaTeX / MathJax

SSE event format:
  data: {"type": "artifact", "artifact_type": "html", "id": "art-1",
         "title": "Login Form", "content": "<form>...</form>", "language": "html"}

Each response can have multiple artifacts. The main text stream is emitted
normally — artifacts are extracted and also emitted as separate events so
clients can choose to show them inline or in a side panel.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Artifact:
    id: str
    artifact_type: str          # html|svg|mermaid|react|code|json|table|math
    content: str
    language: str = ""          # for code artifacts: python, javascript, etc.
    title: str = ""             # auto-generated or extracted from comment


# ── Detection patterns ────────────────────────────────────────────────────────

# Full HTML document or significant HTML fragment
_HTML_RE = re.compile(
    r"```html\s*\n([\s\S]+?)\n```",
    re.IGNORECASE,
)

# SVG
_SVG_RE = re.compile(
    r"```svg\s*\n([\s\S]+?)\n```|(<svg[\s\S]+?</svg>)",
    re.IGNORECASE,
)

# Mermaid diagrams
_MERMAID_RE = re.compile(
    r"```mermaid\s*\n([\s\S]+?)\n```",
    re.IGNORECASE,
)

# React / JSX
_REACT_RE = re.compile(
    r"```(?:jsx?|tsx?|react)\s*\n([\s\S]+?)\n```",
    re.IGNORECASE,
)

# General code blocks (captures language tag)
_CODE_RE = re.compile(
    r"```(\w+)\s*\n([\s\S]+?)\n```",
    re.IGNORECASE,
)

# JSON blocks
_JSON_RE = re.compile(
    r"```json\s*\n([\s\S]+?)\n```",
    re.IGNORECASE,
)

# Markdown tables (3+ column, 3+ row)
_TABLE_RE = re.compile(
    r"(\|[^\n]+\|\n\|[-| :]+\|\n(?:\|[^\n]+\|\n){2,})",
)

# Inline math (LaTeX)
_MATH_BLOCK_RE = re.compile(r"\$\$([\s\S]+?)\$\$")

# Min content length to qualify as artifact (avoid trivial code snippets)
_MIN_ARTIFACT_CHARS = 80

# Non-artifact code languages (too simple to render as artifact)
_SKIP_LANGUAGES = {"bash", "sh", "shell", "zsh", "fish", "cmd", "powershell", "text", "plain"}


def _artifact_id(content: str) -> str:
    return "art-" + hashlib.md5(content.encode()).hexdigest()[:8]


def _extract_title(content: str, artifact_type: str, language: str = "") -> str:
    """Try to infer a title from the content (first comment, function name, etc.)."""
    # HTML: look for <title> tag or first heading
    if artifact_type == "html":
        m = re.search(r"<title>([^<]+)</title>", content, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:60]
        m = re.search(r"<h[1-3][^>]*>([^<]+)</h[1-3]>", content, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:60]

    # Mermaid: look for title directive
    if artifact_type == "mermaid":
        m = re.search(r"title\s+(.+)", content)
        if m:
            return m.group(1).strip()[:60]
        # Use diagram type
        first_line = content.strip().split("\n")[0].strip()
        return first_line[:60] if first_line else "Diagram"

    # Code: look for class/function name or first comment
    if artifact_type == "code":
        m = re.search(r"#\s*(.+)|//\s*(.+)|/\*\*?\s*(.+?)\s*\*/", content)
        if m:
            title = next(g for g in m.groups() if g)
            return title.strip()[:60]
        m = re.search(r"(?:class|function|def|async def|const|export)\s+(\w+)", content)
        if m:
            return f"{m.group(1)} ({language})"

    # React: component name
    if artifact_type == "react":
        m = re.search(r"(?:function|const|class)\s+([A-Z]\w+)", content)
        if m:
            return f"{m.group(1)} component"

    return artifact_type.title()


def extract_artifacts(response: str) -> list[Artifact]:
    """
    Extract all renderable artifacts from a response string.
    Returns list of Artifact objects (may be empty).
    """
    artifacts: list[Artifact] = []
    seen_ids: set[str] = set()

    def _add(artifact_type: str, content: str, language: str = "") -> None:
        content = content.strip()
        if len(content) < _MIN_ARTIFACT_CHARS:
            return
        aid = _artifact_id(content)
        if aid in seen_ids:
            return
        seen_ids.add(aid)
        title = _extract_title(content, artifact_type, language)
        artifacts.append(Artifact(
            id=aid,
            artifact_type=artifact_type,
            content=content,
            language=language,
            title=title,
        ))

    # Priority order matters — more specific patterns first

    # HTML
    for m in _HTML_RE.finditer(response):
        _add("html", m.group(1), "html")

    # SVG
    for m in _SVG_RE.finditer(response):
        content = m.group(1) or m.group(2)
        if content:
            _add("svg", content, "svg")

    # Mermaid
    for m in _MERMAID_RE.finditer(response):
        _add("mermaid", m.group(1))

    # React/JSX
    for m in _REACT_RE.finditer(response):
        lang = m.group(0).split("\n")[0].strip("`").lower()
        _add("react", m.group(1), lang)

    # JSON (before generic code to avoid double-match)
    for m in _JSON_RE.finditer(response):
        _add("json", m.group(1), "json")

    # Generic code blocks (skip already-matched and skip trivial languages)
    for m in _CODE_RE.finditer(response):
        lang = m.group(1).lower()
        content = m.group(2)
        if lang in ("html", "svg", "mermaid", "json") or lang in _SKIP_LANGUAGES:
            continue
        if lang in ("jsx", "tsx", "react"):
            continue
        _add("code", content, lang)

    # Markdown tables
    for m in _TABLE_RE.finditer(response):
        _add("table", m.group(1))

    # Block math
    for m in _MATH_BLOCK_RE.finditer(response):
        _add("math", m.group(1))

    return artifacts


def format_artifact_event(artifact: Artifact) -> dict:
    """Format an artifact as an SSE JSON payload."""
    return {
        "type": "artifact",
        "id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "title": artifact.title,
        "content": artifact.content,
        "language": artifact.language,
    }


def has_artifacts(response: str) -> bool:
    """Quick check — avoids full extraction when response has no artifact markers."""
    return bool(
        re.search(r"```(html|svg|mermaid|jsx?|tsx?|react|json)\s*\n", response, re.IGNORECASE)
        or "<svg" in response
        or "$$" in response
        or _TABLE_RE.search(response)
    )
