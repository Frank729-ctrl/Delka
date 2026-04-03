"""
Code Execution Sandbox — ports Claude Code's Bash tool.

src: Bash tool runs arbitrary shell commands in the user's local environment.
Delka: Safe sandboxed execution of Python, JavaScript, and restricted shell
       commands. Uses subprocess with strict safety filters, restricted PATH,
       and hard time caps.

Safety model:
- Python/JS: no shell=True, blocked dangerous imports
- Bash: command-level blocklist (rm -rf /, sudo, mkfs, dd…), restricted PATH,
        cwd locked to /tmp, timeout 15s, output capped at 8000 chars
- All: run as current server user (non-root assumed), no Docker required

Returns: stdout, stderr, exit_code, execution_time_ms, truncated flag.

Used by: code_service (auto-runs generated code to verify it works),
         notebook_service (cell execution), code_router, sandbox_router.
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
    safety_warning: str = ""   # non-empty if LLM classifier flagged a warn verdict


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


# ── Bash sandbox ─────────────────────────────────────────────────────────────

_BASH_TIMEOUT = 15  # seconds — longer than Python since shell tasks can be slower

# Exact substring / pattern blocklist for shell commands.
# These are irreversible or destructive operations with no legitimate sandbox use.
_BASH_BLOCKED_PATTERNS = re.compile(
    r"""
    (
        rm\s+-[a-z]*r[a-z]*\s+/          # rm -rf / or any recursive rm on /
      | rm\s+-[a-z]*f[a-z]*\s+/          # rm -f /
      | :\(\)\s*\{.*\|.*:.*\}            # fork bomb :(){ :|:& };:
      | \bsudo\b                         # privilege escalation
      | \bsu\s+root\b                    # switch to root
      | \bchmod\s+[0-7]*7\s+/           # chmod 777 / etc.
      | \bchown\b.*\s+/                  # chown on /
      | \bmkfs\b                         # format filesystem
      | \bdd\s+.*of=/dev/               # write to raw device
      | \bshred\b                        # secure delete
      | \bfdisk\b | \bparted\b           # partition editor
      | \biptables\b | \bnftables\b      # firewall tampering
      | \bkill\s+-9\s+-1\b              # kill all processes
      | \bpkill\s+-9\b                   # mass process kill
      | \breboot\b | \bshutdown\b | \bhalt\b | \bpoweroff\b
      | \bcrontab\b                      # cron modification
      | \bsystemctl\b | \bservice\b      # service control
      | \bcurl\b.*\|\s*bash             # curl | bash pipe (arbitrary remote exec)
      | \bwget\b.*\|\s*bash
      | \beval\b                         # eval of dynamic string
      | /etc/passwd | /etc/shadow        # sensitive system files
      | /proc/sys | /sys/                # kernel interfaces
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Commands that are simply not available / not useful in a server sandbox
_BASH_UNAVAILABLE = re.compile(
    r"^\s*(vi|vim|nano|emacs|less|more|top|htop|man|screen|tmux)\b",
    re.IGNORECASE,
)

_BASH_SAFE_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/tmp",
    "TMPDIR": "/tmp",
    "LANG": "en_US.UTF-8",
    "TERM": "xterm-256color",
}

_BASH_MAX_OUTPUT = 8000


def _check_bash_safety(command: str) -> Optional[str]:
    if _BASH_BLOCKED_PATTERNS.search(command):
        return "Command blocked: contains a destructive or privileged operation"
    if _BASH_UNAVAILABLE.match(command):
        return "Interactive programs (vim, less, top…) are not available in the sandbox"
    # Guard against overly long commands (potential injection)
    if len(command) > 2000:
        return "Command too long (max 2,000 chars)"
    return None


async def run_bash(
    command: str,
    timeout: int = _BASH_TIMEOUT,
    env_extras: dict | None = None,
    cwd: str = "/tmp",
) -> SandboxResult:
    """
    Execute a shell command in a restricted sandbox.
    Ports Claude Code's BashTool — safe subset of shell access.

    Args:
        command:     The shell command to run (passed to bash -c)
        timeout:     Max seconds (default 15, max 30)
        env_extras:  Additional safe env vars to inject (no PATH override)
        cwd:         Working directory, must be under /tmp (enforced)
    """
    result = SandboxResult(language="bash")

    # Enforce safe cwd
    import os.path as _op
    cwd = cwd if cwd.startswith("/tmp") else "/tmp"

    block_reason = _check_bash_safety(command)
    if block_reason:
        result.blocked = True
        result.block_reason = block_reason
        return result

    # ── Tier 2: LLM speculative safety classifier ─────────────────────────────
    # Only fires for commands that passed the regex blocklist but look ambiguous.
    # Fail-open: classifier timeout/error → proceed as safe.
    from services.bash_safety_service import classify_command, format_warning
    safety = await classify_command(command)
    if safety.verdict == "block":
        result.blocked = True
        result.block_reason = f"Safety classifier blocked: {safety.reason}"
        return result
    if safety.verdict == "warn":
        # Run the command but attach a warning to the result
        result.safety_warning = format_warning(safety, command)
    # safety.verdict == "safe" → proceed normally

    timeout = min(max(1, timeout), 30)   # clamp 1–30s

    env = {**_BASH_SAFE_ENV}
    if env_extras:
        # Only allow safe keys — no PATH, LD_PRELOAD, etc.
        _safe_keys = re.compile(r"^[A-Z][A-Z0-9_]{0,30}$")
        _blocked_env = {"PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONPATH",
                        "HOME", "SHELL", "USER", "LOGNAME"}
        for k, v in env_extras.items():
            if _safe_keys.match(k) and k not in _blocked_env:
                env[k] = str(v)[:500]

    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            "/bin/bash", "-c", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=cwd,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            result.stderr = f"Command timed out after {timeout}s"
            result.exit_code = 124
            result.execution_ms = round((time.time() - start) * 1000, 1)
            return result

        result.execution_ms = round((time.time() - start) * 1000, 1)
        result.exit_code = proc.returncode if proc.returncode is not None else 0

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        combined = stdout
        if stderr.strip():
            combined += f"\n[stderr]:\n{stderr}"

        if len(combined) > _BASH_MAX_OUTPUT:
            result.stdout = combined[:_BASH_MAX_OUTPUT]
            result.truncated = True
        else:
            result.stdout = combined
        result.stderr = stderr.strip()

    except FileNotFoundError:
        result.stderr = "/bin/bash not found on this system"
        result.exit_code = 127
    except Exception as exc:
        result.stderr = str(exc)[:300]
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
    elif lang in ("bash", "sh", "shell"):
        return await run_bash(code)
    else:
        result = SandboxResult(language=lang)
        result.blocked = True
        result.block_reason = f"Language '{lang}' not supported in sandbox (python, javascript, bash)"
        return result


def format_sandbox_result(result: SandboxResult) -> str:
    """Format execution result as markdown to append to code response."""
    if result.blocked:
        return f"\n_🔒 Sandbox: {result.block_reason}_"
    if result.safety_warning:
        return f"\n{result.safety_warning}"

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
