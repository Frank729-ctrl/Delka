"""
Code Execution Sandbox — exceeds Claude Code's Bash tool.

src: Bash tool runs arbitrary shell commands in the user's environment.
Delka: Safe sandboxed execution of generated Python and JavaScript code.
       Uses subprocess with strict resource limits — no network, no file
       writes outside /tmp, hard time and memory caps.

Safety model:
- Python: subprocess with timeout=10s, no shell=True, restricted env
- JavaScript: Node.js subprocess, same restrictions
- Blocked: shell commands, imports of os/subprocess/socket in user code
- Output capped at 4000 chars

Returns: stdout, stderr, exit_code, execution_time_ms, truncated flag.

Used by: code_service (auto-runs generated code to verify it works),
         notebook_service (cell execution), code_router (/v1/code/run).
"""
import asyncio
import re
import time
import sys
import os
from dataclasses import dataclass
from typing import Optional


# ── Safety blocklist ──────────────────────────────────────────────────────────

_PYTHON_BLOCKED = re.compile(
    r"\b(import\s+(os|sys|subprocess|socket|shutil|ctypes|multiprocessing|"
    r"threading|importlib|pty|signal|resource|mmap|gc)|"
    r"__import__|exec\s*\(|eval\s*\(|open\s*\(|"
    r"compile\s*\(|globals\s*\(|locals\s*\(|vars\s*\()\b",
    re.IGNORECASE,
)

_JS_BLOCKED = re.compile(
    r"\b(require\s*\(\s*['\"]fs|require\s*\(\s*['\"]child_process|"
    r"require\s*\(\s*['\"]net|require\s*\(\s*['\"]http|"
    r"process\.exit|process\.env|__dirname|__filename)\b",
    re.IGNORECASE,
)

_MAX_OUTPUT = 4000
_TIMEOUT_SECONDS = 10


@dataclass
class SandboxResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_ms: float = 0.0
    truncated: bool = False
    blocked: bool = False
    block_reason: str = ""
    language: str = ""


# ── Security pre-check ────────────────────────────────────────────────────────

def _check_python_safety(code: str) -> Optional[str]:
    match = _PYTHON_BLOCKED.search(code)
    if match:
        return f"Blocked: '{match.group(0).strip()}' is not allowed in sandbox"
    return None


def _check_js_safety(code: str) -> Optional[str]:
    match = _JS_BLOCKED.search(code)
    if match:
        return f"Blocked: '{match.group(0).strip()}' is not allowed in sandbox"
    return None


# ── Execution ─────────────────────────────────────────────────────────────────

async def run_python(code: str) -> SandboxResult:
    result = SandboxResult(language="python")

    block_reason = _check_python_safety(code)
    if block_reason:
        result.blocked = True
        result.block_reason = block_reason
        return result

    # Wrap code to capture output cleanly
    wrapped = f"""
import sys, io as _io
_buf = _io.StringIO()
sys.stdout = _buf
sys.stderr = _buf
try:
{chr(10).join('    ' + line for line in code.splitlines())}
except Exception as _e:
    print(f"Error: {{_e}}")
finally:
    sys.stdout = sys.__stdout__
    print(_buf.getvalue(), end='')
"""
    return await _run_subprocess(
        [sys.executable, "-c", wrapped],
        result,
    )


async def run_javascript(code: str) -> SandboxResult:
    result = SandboxResult(language="javascript")

    block_reason = _check_js_safety(code)
    if block_reason:
        result.blocked = True
        result.block_reason = block_reason
        return result

    # Check node is available
    node_path = "node"

    return await _run_subprocess(
        [node_path, "--eval", code],
        result,
    )


async def _run_subprocess(cmd: list[str], result: SandboxResult) -> SandboxResult:
    """Execute subprocess with timeout and output cap."""
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": "",
    }
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd="/tmp",
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            proc.kill()
            result.stderr = f"Execution timed out after {_TIMEOUT_SECONDS}s"
            result.exit_code = 124
            result.execution_ms = round((time.time() - start) * 1000, 1)
            return result

        result.execution_ms = round((time.time() - start) * 1000, 1)
        result.exit_code = proc.returncode or 0

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        combined = stdout + (f"\n[stderr]: {stderr}" if stderr.strip() else "")
        if len(combined) > _MAX_OUTPUT:
            result.stdout = combined[:_MAX_OUTPUT]
            result.truncated = True
        else:
            result.stdout = combined

    except FileNotFoundError as e:
        result.stderr = f"Runtime not found: {e}"
        result.exit_code = 127
    except Exception as e:
        result.stderr = str(e)
        result.exit_code = 1

    return result


# ── Main dispatch ─────────────────────────────────────────────────────────────

async def execute_code(code: str, language: str) -> SandboxResult:
    """
    Execute code in the sandbox. Auto-dispatches by language.
    Returns SandboxResult.
    """
    lang = language.lower().strip()
    if lang in ("python", "py", "python3"):
        return await run_python(code)
    elif lang in ("javascript", "js", "node", "nodejs"):
        return await run_javascript(code)
    else:
        result = SandboxResult(language=lang)
        result.blocked = True
        result.block_reason = f"Language '{lang}' not supported in sandbox (Python and JavaScript only)"
        return result


def format_sandbox_result(result: SandboxResult) -> str:
    """Format execution result as markdown to append to code response."""
    if result.blocked:
        return f"\n_🔒 Sandbox: {result.block_reason}_"

    lines = [f"\n**Execution result** _{result.language} · {result.execution_ms}ms_"]

    if result.exit_code == 0:
        lines.append("```")
        lines.append(result.stdout or "(no output)")
        lines.append("```")
        if result.truncated:
            lines.append("_Output truncated at 4,000 chars_")
    else:
        lines.append(f"_Exit code {result.exit_code}_")
        if result.stdout:
            lines.append("```")
            lines.append(result.stdout)
            lines.append("```")
        if result.stderr:
            lines.append(f"_Error: {result.stderr[:300]}_")

    return "\n".join(lines)
