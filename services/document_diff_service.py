"""
Document Diff — exceeds Claude Code's diff/patch visualization.

src: Shows unified diffs of file edits so users see exactly what changed.
Delka: Generates structured before/after diffs for CV edits, cover letters,
       and any document rewrite. Returns both a human-readable diff summary
       AND a machine-readable patch so frontends can show tracked-changes UI.

Diff formats:
1. Word-level diff  — "changed X → Y" for each modified sentence
2. Section diff     — which sections were added/removed/rewritten
3. Stats summary    — words added, words removed, % change
4. Unified patch    — standard unified diff for frontends that render it

Used by: cv_router, cover_letter_router, doc_router, and any
         service that rewrites user documents.
"""
import re
import difflib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DiffResult:
    added_words: int = 0
    removed_words: int = 0
    unchanged_words: int = 0
    change_pct: float = 0.0
    section_changes: list[dict] = field(default_factory=list)   # {section, change_type}
    word_changes: list[dict] = field(default_factory=list)      # {old, new, context}
    unified_patch: str = ""
    summary: str = ""


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _split_sections(text: str) -> dict[str, str]:
    """
    Split a document into named sections (for CVs/letters).
    Detects headers like "EXPERIENCE", "EDUCATION", "Summary:", etc.
    """
    section_re = re.compile(
        r"^(#{1,3}\s+.+|[A-Z][A-Z\s]{3,}:|(?:Summary|Experience|Education|Skills|"
        r"Projects|Certifications|Languages|References|Objective|Profile|Contact)\s*:?)\s*$",
        re.MULTILINE,
    )
    sections = {}
    parts = section_re.split(text)

    current = "preamble"
    for part in parts:
        if section_re.match(part.strip()):
            current = part.strip().rstrip(":").strip()
        else:
            if current not in sections:
                sections[current] = ""
            sections[current] += part

    return {k: v.strip() for k, v in sections.items() if v.strip()}


def diff_documents(original: str, revised: str) -> DiffResult:
    """
    Compare two versions of a document and produce a full DiffResult.
    """
    result = DiffResult()

    # ── 1. Unified patch ──────────────────────────────────────────────────────
    orig_lines = original.splitlines(keepends=True)
    rev_lines = revised.splitlines(keepends=True)
    result.unified_patch = "".join(difflib.unified_diff(
        orig_lines, rev_lines,
        fromfile="original", tofile="revised", lineterm="",
    ))

    # ── 2. Word-level stats ───────────────────────────────────────────────────
    orig_words = original.split()
    rev_words = revised.split()
    sm = difflib.SequenceMatcher(None, orig_words, rev_words)

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            result.unchanged_words += i2 - i1
        elif op == "insert":
            result.added_words += j2 - j1
        elif op == "delete":
            result.removed_words += i2 - i1
        elif op == "replace":
            result.removed_words += i2 - i1
            result.added_words += j2 - j1
            # Capture meaningful word changes (skip tiny noise)
            old_chunk = " ".join(orig_words[i1:i2])
            new_chunk = " ".join(rev_words[j1:j2])
            if len(old_chunk) > 4 or len(new_chunk) > 4:
                context_start = max(0, i1 - 3)
                context = " ".join(orig_words[context_start:i1])
                result.word_changes.append({
                    "old": old_chunk[:120],
                    "new": new_chunk[:120],
                    "context": context[-60:],
                })

    total = result.added_words + result.removed_words + result.unchanged_words
    if total > 0:
        result.change_pct = round(
            (result.added_words + result.removed_words) / total * 100, 1
        )

    # ── 3. Section-level changes ──────────────────────────────────────────────
    orig_sections = _split_sections(original)
    rev_sections = _split_sections(revised)
    all_sections = set(orig_sections) | set(rev_sections)

    for section in all_sections:
        o = orig_sections.get(section, "")
        r = rev_sections.get(section, "")
        if not o and r:
            result.section_changes.append({"section": section, "change": "added"})
        elif o and not r:
            result.section_changes.append({"section": section, "change": "removed"})
        elif o != r:
            # Compute section similarity
            ratio = difflib.SequenceMatcher(None, o, r).ratio()
            change = "rewritten" if ratio < 0.5 else "edited"
            result.section_changes.append({"section": section, "change": change, "similarity": round(ratio, 2)})

    # ── 4. Human-readable summary ─────────────────────────────────────────────
    parts = []
    if result.added_words:
        parts.append(f"+{result.added_words} words added")
    if result.removed_words:
        parts.append(f"-{result.removed_words} words removed")
    parts.append(f"{result.change_pct}% changed")

    section_notes = []
    for sc in result.section_changes:
        section_notes.append(f"{sc['section']} ({sc['change']})")
    if section_notes:
        parts.append("Sections: " + ", ".join(section_notes))

    result.summary = " · ".join(parts)
    return result


def format_diff_for_response(result: DiffResult, show_patch: bool = False) -> str:
    """Format DiffResult as markdown to append to a document rewrite response."""
    lines = ["\n**Document changes:**", f"_{result.summary}_"]

    if result.section_changes:
        lines.append("\nSection changes:")
        for sc in result.section_changes:
            icon = {"added": "🟢", "removed": "🔴", "rewritten": "🔵", "edited": "🟡"}.get(sc["change"], "•")
            lines.append(f"- {icon} **{sc['section']}** — {sc['change']}")

    if result.word_changes and len(result.word_changes) <= 5:
        lines.append("\nKey edits:")
        for wc in result.word_changes[:5]:
            lines.append(f"- ~~{wc['old']}~~ → **{wc['new']}**")

    if show_patch and result.unified_patch:
        lines.append("\n```diff")
        lines.append(result.unified_patch[:3000])
        lines.append("```")

    return "\n".join(lines)


def get_diff_sse_event(result: DiffResult) -> str:
    """SSE event so frontend can render a live diff panel."""
    import json
    return f"data: {json.dumps({'type': 'document_diff', 'summary': result.summary, 'sections': result.section_changes, 'added': result.added_words, 'removed': result.removed_words, 'change_pct': result.change_pct})}\n\n"
