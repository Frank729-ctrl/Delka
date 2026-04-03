"""
Bash Speculative Safety Classifier — exceeds Claude Code's bashSecurity.ts.

src has 6 safety layers for bash:
  bashPermissions.ts    — permission mode gate
  bashSecurity.ts       — command blocklist + sed parser
  readOnlyValidation.ts — detects write ops in read-only mode
  destructiveCommandWarning.ts — warns before irreversible ops
  sedValidation.ts      — parses and validates sed expressions
  shouldUseSandbox.ts   — decides subprocess vs docker

Delka already has layer 1: 15-pattern regex blocklist in code_sandbox_service.
This adds layer 2: LLM speculative classifier for commands that PASS the regex
but are still potentially destructive or suspicious.

Why LLM instead of more regex:
  - Regex can't catch obfuscated commands:
      python -c "import os; os.system('rm -rf /')"
      base64 -d <<< "cm0gLXJmIC8=" | bash
      find /home -perm /222 -exec rm {} \;
      chmod -R 000 /etc
  - Regex can't understand context (intent matters)
  - LLM classifies intent + gives a clear reason

Three-verdict system (matches src's approach):
  safe        → run the command
  warn        → run but emit a warning SSE event (reversible but noteworthy)
  block       → refuse to run (irreversible or clearly malicious)

The classifier uses a fast small model (Groq 8b) with a structured prompt
and a 3-second timeout. If the classifier fails or times out, we default
to SAFE (fail-open — don't break the user experience for benign commands).

Caching: identical commands are cached for the process lifetime to avoid
redundant API calls for repeated commands.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Optional

# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class SafetyVerdict:
    verdict: str           # safe | warn | block
    reason: str            # human-readable explanation
    risk_level: int        # 0=safe, 1=low, 2=medium, 3=high, 4=critical
    is_cached: bool = False


_SAFE = SafetyVerdict(verdict="safe", reason="Command appears safe", risk_level=0)

# ── Heuristic pre-filter ──────────────────────────────────────────────────────
# Fast checks before spending an LLM call — catches obvious safe cases
# and escalates genuinely ambiguous ones.

_OBVIOUSLY_SAFE_RE = re.compile(
    r"""
    ^(
        ls(\s+-[lahS]+)?(\s+\S+)?       # ls, ls -la, ls /tmp
      | pwd
      | echo\s
      | cat\s+[\w./\-]+                 # cat a single file path
      | head(\s+-\d+)?\s+\S+
      | tail(\s+-\d+)?\s+\S+
      | wc\s+
      | grep\s+
      | find\s+.*\s+-name\s+            # find ... -name (read-only intent)
      | which\s+\w+
      | whoami
      | hostname
      | date
      | uname(\s+-\w+)?
      | env(\s+\w+=)?
      | printenv
      | python\s+(--version|-V)
      | node\s+(--version|-v)
      | pip\s+(list|show|freeze)
      | git\s+(status|log|diff|show|branch|remote|config\s+--list)
      | df\s+
      | du\s+
      | free
      | uptime
      | ps(\s+-\w+)?
      | top\s+-b
      | curl\s+-[sI]                    # curl -s (silent) or -I (head only)
      | wget\s+--spider
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_NEEDS_CLASSIFIER_RE = re.compile(
    r"""
    (
        rm\s+           # any rm (non-recursive already blocked, but rm file is warn)
      | chmod\s+
      | chown\s+
      | mv\s+.*\s+/   # move to /
      | cp\s+.*\s+/   # copy to /
      | find\s+.*-(delete|exec\s+rm)  # find with delete
      | curl\s+.*\|    # curl piped (non-bash already blocked, but partial)
      | wget\s+.*-O\s+-  # wget stdout redirect
      | python\s+-c    # inline python exec
      | perl\s+-e      # inline perl exec
      | node\s+-e      # inline node exec
      | base64\s+-d    # base64 decode (potential obfuscation)
      | xxd\s+         # hex dump tool
      | truncate\s+
      | dd\s+          # dd (of=/dev/ blocked, but dd if=/dev/zero of=file is warn)
      | mktemp\s+
      | install\s+     # file installation
      | ln\s+          # symlinks
      | mount\s+       # mount ops
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# ── In-process cache ──────────────────────────────────────────────────────────

_verdict_cache: dict[str, SafetyVerdict] = {}
_MAX_CACHE = 500


def _cache_key(command: str) -> str:
    return hashlib.md5(command.strip().encode()).hexdigest()


def _get_cached(command: str) -> Optional[SafetyVerdict]:
    v = _verdict_cache.get(_cache_key(command))
    if v:
        return SafetyVerdict(
            verdict=v.verdict, reason=v.reason,
            risk_level=v.risk_level, is_cached=True,
        )
    return None


def _set_cached(command: str, verdict: SafetyVerdict) -> None:
    if len(_verdict_cache) >= _MAX_CACHE:
        # Evict oldest 100
        keys = list(_verdict_cache.keys())[:100]
        for k in keys:
            del _verdict_cache[k]
    _verdict_cache[_cache_key(command)] = verdict


# ── LLM classifier ────────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM = """\
You are a shell command safety classifier for a sandboxed server environment.
The sandbox runs as a non-root user, cwd=/tmp, restricted PATH.

Classify the given shell command with ONE of these verdicts:
  safe   - benign, read-only or clearly harmless write to /tmp
  warn   - potentially destructive, reversible, or modifies important files
  block  - irreversible, clearly malicious, privilege escalation, or obfuscated attack

Respond with ONLY valid JSON, no other text:
{
  "verdict": "safe"|"warn"|"block",
  "reason": "one sentence explanation",
  "risk_level": 0-4
}

Risk levels: 0=safe, 1=low, 2=medium, 3=high, 4=critical

Examples:
  "ls -la /tmp" → {"verdict":"safe","reason":"Read-only directory listing","risk_level":0}
  "rm /tmp/test.py" → {"verdict":"warn","reason":"Deletes a file, but limited to /tmp","risk_level":1}
  "chmod -R 777 /var/www" → {"verdict":"block","reason":"Grants world-write on web root","risk_level":3}
  "python -c \\"import os;os.system('rm -rf /')\\"" → {"verdict":"block","reason":"Obfuscated rm -rf /","risk_level":4}
  "find /home -name '*.log' -delete" → {"verdict":"warn","reason":"Bulk delete outside /tmp","risk_level":2}
"""

_VERDICT_RE = re.compile(r'"verdict"\s*:\s*"(safe|warn|block)"')
_REASON_RE = re.compile(r'"reason"\s*:\s*"([^"]+)"')
_RISK_RE = re.compile(r'"risk_level"\s*:\s*(\d)')


def _parse_verdict(text: str) -> Optional[SafetyVerdict]:
    """Extract verdict from LLM response — tolerant of partial JSON."""
    v_match = _VERDICT_RE.search(text)
    r_match = _REASON_RE.search(text)
    risk_match = _RISK_RE.search(text)
    if not v_match:
        return None
    return SafetyVerdict(
        verdict=v_match.group(1),
        reason=r_match.group(1) if r_match else "LLM classified this command",
        risk_level=int(risk_match.group(1)) if risk_match else 1,
    )


async def _llm_classify(command: str) -> SafetyVerdict:
    """Call a fast LLM to classify command safety. Times out in 3s → default safe."""
    try:
        from services.inference_service import generate_full_response
        response, _, _ = await asyncio.wait_for(
            generate_full_response(
                task="chat",
                system_prompt=_CLASSIFIER_SYSTEM,
                user_prompt=f"Classify this command:\n{command}",
                temperature=0.0,
                max_tokens=150,
            ),
            timeout=3.0,
        )
        verdict = _parse_verdict(response)
        return verdict if verdict else _SAFE
    except (asyncio.TimeoutError, Exception):
        # Classifier failure → fail-open (safe)
        return _SAFE


# ── Public API ────────────────────────────────────────────────────────────────

async def classify_command(command: str) -> SafetyVerdict:
    """
    Three-tier safety check for a bash command:
      1. Cache hit → return immediately
      2. Obviously safe pattern → skip LLM, return safe
      3. Needs classifier pattern → call LLM
      4. Neither → return safe (benign default)

    The regex blocklist in code_sandbox_service is tier 0 (runs before this).
    This is tier 1 — for commands that passed the blocklist but may still be risky.
    """
    # 1. Cache
    cached = _get_cached(command)
    if cached:
        return cached

    verdict: SafetyVerdict

    # 2. Obviously safe — skip LLM
    if _OBVIOUSLY_SAFE_RE.match(command.strip()):
        verdict = SafetyVerdict(verdict="safe", reason="Matches known-safe pattern", risk_level=0)

    # 3. Ambiguous — call LLM classifier
    elif _NEEDS_CLASSIFIER_RE.search(command):
        verdict = await _llm_classify(command)

    # 4. Default safe
    else:
        verdict = _SAFE

    _set_cached(command, verdict)
    return verdict


def format_warning(verdict: SafetyVerdict, command: str) -> str:
    """Format a user-facing warning for warn-verdict commands."""
    risk_label = {0: "low", 1: "low", 2: "medium", 3: "high", 4: "critical"}.get(verdict.risk_level, "unknown")
    return (
        f"⚠️ **Command safety warning** (risk: {risk_label})\n"
        f"Command: `{command[:100]}`\n"
        f"Reason: {verdict.reason}\n"
        f"_The command was executed. Review output carefully._"
    )
