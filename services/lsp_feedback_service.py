"""
LSP Feedback Service — exceeds Claude Code's LSP diagnosticTracking.ts.

src: Reads Language Server Protocol diagnostics from the IDE in real time
     (errors, warnings from language servers like Pylance, ESLint).
Delka: No IDE needed. Streams real-time diagnostic feedback AS code is being
       generated, token by token. Uses an incremental analysis approach:
       - Accumulates tokens into a buffer
       - Runs lightweight checks every N tokens or when a code block closes
       - Emits SSE diagnostic events that frontend can show as inline markers
       - Final full diagnostics run when generation completes

Three analysis passes:
1. FAST (every 30 tokens): syntax-level quick checks (unmatched brackets,
   obvious errors) — <1ms, runs inline during streaming
2. MEDIUM (on code block close): structure checks (function signatures,
   missing returns, import issues) — runs after ``` marker
3. FULL (after generation): complete code_diagnostics_service run — same
   as before but now the user sees it arrive incrementally

Gives users live feedback like an IDE, not just a static note at the end.
"""
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StreamDiagnostic:
    severity: str           # "error" | "warning" | "info"
    message: str
    line_hint: Optional[int] = None
    pass_level: str = "fast"   # "fast" | "medium" | "full"


@dataclass
class LSPStreamState:
    """Stateful accumulator for a streaming code generation response."""
    buffer: str = ""
    token_count: int = 0
    in_code_block: bool = False
    code_language: str = ""
    code_buffer: str = ""
    diagnostics: list[StreamDiagnostic] = field(default_factory=list)
    last_fast_check_at: int = 0
    _FAST_INTERVAL = 30   # tokens between fast checks


# ── Fast checks (inline, every 30 tokens) ────────────────────────────────────

def _fast_check(code_so_far: str, language: str) -> list[StreamDiagnostic]:
    """Quick structural checks that run during streaming. Must be <1ms."""
    diags = []

    if language in ("python", "py"):
        # Unmatched parens/brackets (quick count)
        opens = code_so_far.count("(") - code_so_far.count(")")
        if opens > 3:
            diags.append(StreamDiagnostic("warning", f"Possible unclosed parenthesis ({opens} open)", pass_level="fast"))

        # Obvious indentation issue: def/class with no body yet
        if re.search(r"^(def|class)\s+\w+[^:]*:\s*$", code_so_far, re.MULTILINE):
            if not re.search(r"^(def|class)\s+\w+[^:]*:\s*\n\s+\S", code_so_far, re.MULTILINE):
                diags.append(StreamDiagnostic("info", "Function/class body expected — still generating", pass_level="fast"))

    elif language in ("javascript", "js", "typescript", "ts"):
        opens = code_so_far.count("{") - code_so_far.count("}")
        if opens > 4:
            diags.append(StreamDiagnostic("warning", f"Possible unclosed block ({opens} open braces)", pass_level="fast"))

    return diags


# ── Medium checks (on code block close) ──────────────────────────────────────

def _medium_check(code: str, language: str) -> list[StreamDiagnostic]:
    """Structure checks run when a code block is completed."""
    diags = []

    if language in ("python", "py"):
        # Functions with no return type or missing return
        funcs = re.findall(r"def\s+(\w+)\s*\([^)]*\)\s*:", code)
        for fname in funcs:
            body_pattern = rf"def\s+{re.escape(fname)}\s*\([^)]*\)\s*:.*?(?=\ndef|\Z)"
            body_match = re.search(body_pattern, code, re.DOTALL)
            if body_match:
                body = body_match.group(0)
                if "return" not in body and fname not in ("__init__", "setUp", "tearDown"):
                    diags.append(StreamDiagnostic("info", f"'{fname}()' has no return statement", pass_level="medium"))

        # Missing imports
        if "pd." in code and "import pandas" not in code:
            diags.append(StreamDiagnostic("warning", "pandas used but not imported", pass_level="medium"))
        if "np." in code and "import numpy" not in code:
            diags.append(StreamDiagnostic("warning", "numpy used but not imported", pass_level="medium"))
        if "plt." in code and "import matplotlib" not in code:
            diags.append(StreamDiagnostic("warning", "matplotlib used but not imported", pass_level="medium"))
        if re.search(r"\brequests\.", code) and "import requests" not in code:
            diags.append(StreamDiagnostic("warning", "requests used but not imported", pass_level="medium"))

    elif language in ("javascript", "js"):
        # async function without await
        if re.search(r"async\s+function", code) and "await" not in code:
            diags.append(StreamDiagnostic("info", "async function with no await — may not need async", pass_level="medium"))

        # Promise without catch
        if ".then(" in code and ".catch(" not in code:
            diags.append(StreamDiagnostic("warning", "Promise .then() without .catch() — add error handling", pass_level="medium"))

    return diags


# ── Stream processor ──────────────────────────────────────────────────────────

def process_token(state: LSPStreamState, token: str) -> list[str]:
    """
    Process one streaming token. Returns a list of SSE strings to emit
    (may be empty, or contain diagnostic events).
    """
    import json
    state.buffer += token
    state.token_count += 1
    sse_events = []

    # Detect code block boundaries
    if "```" in state.buffer:
        # Check for opening code block
        if not state.in_code_block:
            match = re.search(r"```(\w*)\n?", state.buffer)
            if match:
                state.in_code_block = True
                state.code_language = match.group(1) or "python"
                state.code_buffer = ""
        else:
            # Check for closing
            if state.buffer.rstrip().endswith("```"):
                # Code block complete — run medium check
                diags = _medium_check(state.code_buffer, state.code_language)
                for d in diags:
                    if d not in state.diagnostics:
                        state.diagnostics.append(d)
                        sse_events.append(
                            f"data: {json.dumps({'type': 'lsp_diagnostic', 'severity': d.severity, 'message': d.message, 'pass': d.pass_level})}\n\n"
                        )
                state.in_code_block = False
                state.code_buffer = ""

    # Accumulate code if inside block
    if state.in_code_block and "```" not in token:
        state.code_buffer += token

    # Fast check every N tokens (only while inside a code block)
    if (state.in_code_block
            and state.code_buffer
            and state.token_count - state.last_fast_check_at >= state.last_fast_check_at + state._FAST_INTERVAL):
        state.last_fast_check_at = state.token_count
        for d in _fast_check(state.code_buffer, state.code_language):
            # Only emit new diagnostics (deduplicate by message)
            if not any(x.message == d.message for x in state.diagnostics):
                state.diagnostics.append(d)
                sse_events.append(
                    f"data: {json.dumps({'type': 'lsp_diagnostic', 'severity': d.severity, 'message': d.message, 'pass': d.pass_level})}\n\n"
                )

    return sse_events


def finalize(state: LSPStreamState, full_response: str) -> list[str]:
    """
    Run full diagnostics on completed response. Returns SSE events for any
    new issues not already emitted during streaming.
    """
    import json
    from services.code_diagnostics_service import diagnose_code

    # Extract all code blocks from full response
    blocks = re.findall(r"```(\w*)\n([\s\S]*?)```", full_response)
    sse_events = []

    for lang, code in blocks:
        if not lang:
            lang = "python"
        result = diagnose_code(code, lang)
        all_issues = (
            [("error", e) for e in result.errors]
            + [("warning", s) for s in result.security_issues]
            + [("info", w) for w in result.warnings]
        )
        for severity, msg in all_issues:
            if not any(x.message == msg for x in state.diagnostics):
                state.diagnostics.append(StreamDiagnostic(severity, msg, pass_level="full"))
                sse_events.append(
                    f"data: {json.dumps({'type': 'lsp_diagnostic', 'severity': severity, 'message': msg, 'pass': 'full'})}\n\n"
                )

    # Emit confidence score
    if blocks:
        error_count = sum(1 for d in state.diagnostics if d.severity == "error")
        warn_count = sum(1 for d in state.diagnostics if d.severity == "warning")
        score = max(0, round(1.0 - error_count * 0.3 - warn_count * 0.05, 2))
        sse_events.append(
            f"data: {json.dumps({'type': 'lsp_confidence', 'score': score, 'total_diagnostics': len(state.diagnostics)})}\n\n"
        )

    return sse_events
