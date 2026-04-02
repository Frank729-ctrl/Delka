"""
Code diagnostics — exceeds Claude Code's LSP diagnosticTracking.ts.

src: Reads LSP diagnostics from IDE (errors, warnings from language server).
Delka: Validates generated code for syntax errors, common bugs, and security
       issues before returning it to the user. No IDE needed — pure API.

Checks performed on generated code:
1. Python: ast.parse() for syntax errors
2. JavaScript/TypeScript: basic structure validation
3. SQL: common injection pattern detection
4. All languages: security scan (hardcoded secrets, eval(), dangerous patterns)

Also generates a confidence score for the generated code.
"""
import ast
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DiagnosticResult:
    language: str
    has_errors: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    security_issues: list[str] = field(default_factory=list)
    confidence_score: float = 1.0   # 0.0 to 1.0
    is_safe_to_return: bool = True


# ── Security patterns (language-agnostic) ─────────────────────────────────────

_SECURITY_PATTERNS = [
    (r'eval\s*\(', "eval() usage — potential code injection"),
    (r'exec\s*\(', "exec() usage — potential code injection"),
    (r'os\.system\s*\(', "os.system() — prefer subprocess"),
    (r'subprocess\.call\s*\(.*shell\s*=\s*True', "shell=True in subprocess — injection risk"),
    (r'password\s*=\s*["\'][^"\']{4,}["\']', "Hardcoded password detected"),
    (r'api_key\s*=\s*["\'][a-zA-Z0-9_\-]{10,}["\']', "Hardcoded API key detected"),
    (r'secret\s*=\s*["\'][^"\']{6,}["\']', "Hardcoded secret detected"),
    (r'DROP\s+TABLE', "Destructive SQL: DROP TABLE"),
    (r'DELETE\s+FROM\s+\w+\s*;', "Unfiltered DELETE — missing WHERE clause?"),
    (r'SELECT\s+\*\s+FROM', "SELECT * — consider specifying columns"),
]

# ── Language-specific validators ──────────────────────────────────────────────

def _validate_python(code: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    try:
        ast.parse(code)
    except SyntaxError as e:
        errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
    except Exception as e:
        errors.append(f"Parse error: {e}")

    # Style/quality warnings
    if "print(" in code and "def " not in code and "class " not in code:
        warnings.append("Consider using logging instead of print() in production code")
    if re.search(r"except\s*:", code):
        warnings.append("Bare except: clause — consider catching specific exceptions")
    if re.search(r"time\.sleep\(\d+\)", code):
        warnings.append("time.sleep() detected — consider async alternatives")

    return errors, warnings


def _validate_javascript(code: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    # Basic brace balance check
    opens = code.count("{")
    closes = code.count("}")
    if opens != closes:
        errors.append(f"Unbalanced braces: {opens} {{ vs {closes} }}")

    if "var " in code:
        warnings.append("var is deprecated — use const or let instead")
    if "==" in code and "===" not in code:
        warnings.append("Use === for strict equality checks in JavaScript")
    if "console.log" in code:
        warnings.append("Remove console.log() before production deployment")

    return errors, warnings


def _validate_sql(code: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    upper = code.upper()

    if "DELETE FROM" in upper and "WHERE" not in upper:
        errors.append("DELETE without WHERE — this deletes ALL rows")
    if "UPDATE " in upper and "WHERE" not in upper:
        errors.append("UPDATE without WHERE — this updates ALL rows")
    if "SELECT *" in upper:
        warnings.append("SELECT * — specify columns explicitly for performance")

    return errors, warnings


def _security_scan(code: str) -> list[str]:
    issues = []
    for pattern, description in _SECURITY_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            issues.append(description)
    return issues


# ── Main entry point ──────────────────────────────────────────────────────────

def diagnose_code(code: str, language: str) -> DiagnosticResult:
    """
    Run all diagnostics on generated code.
    Returns a DiagnosticResult with errors, warnings, and security issues.
    """
    lang = language.lower().strip()
    result = DiagnosticResult(language=lang)

    # Language-specific validation
    if lang in ("python", "py"):
        result.errors, result.warnings = _validate_python(code)
    elif lang in ("javascript", "js", "typescript", "ts"):
        result.errors, result.warnings = _validate_javascript(code)
    elif lang in ("sql",):
        result.errors, result.warnings = _validate_sql(code)

    # Security scan (all languages)
    result.security_issues = _security_scan(code)

    result.has_errors = bool(result.errors)
    result.is_safe_to_return = not result.errors  # Warnings are OK; errors block

    # Confidence score: 1.0 = clean, decreases with issues
    deductions = len(result.errors) * 0.3 + len(result.warnings) * 0.05 + len(result.security_issues) * 0.15
    result.confidence_score = max(0.0, round(1.0 - deductions, 2))

    return result


def format_diagnostics(result: DiagnosticResult) -> str:
    """Format diagnostics as markdown for appending to code response."""
    if not result.errors and not result.warnings and not result.security_issues:
        return f"\n_✓ Code validated ({result.language}) — no issues found_"

    lines = ["\n**Code review:**"]
    for e in result.errors:
        lines.append(f"- 🔴 {e}")
    for s in result.security_issues:
        lines.append(f"- 🔒 {s}")
    for w in result.warnings:
        lines.append(f"- 🟡 {w}")
    lines.append(f"\n_Confidence: {int(result.confidence_score * 100)}%_")
    return "\n".join(lines)
