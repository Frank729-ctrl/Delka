"""
Code sandbox router — execute code and shell commands safely.

POST /v1/code/run   — execute Python, JavaScript, or Bash (language field)
POST /v1/code/bash  — dedicated Bash endpoint with timeout + env control
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from services.code_sandbox_service import execute_code, run_bash, format_sandbox_result

router = APIRouter(prefix="/v1/code")


class RunRequest(BaseModel):
    code: str
    language: str = "python"   # "python" | "javascript" | "bash"


class BashRequest(BaseModel):
    command: str = Field(..., description="Shell command to execute")
    timeout: int = Field(15, ge=1, le=30, description="Max seconds (1–30)")
    env: Optional[dict] = Field(None, description="Extra environment variables (safe keys only)")
    description: Optional[str] = Field(None, description="Human-readable description of what this does")


def _result_response(result) -> dict:
    return {
        "status": "ok",
        "language": result.language,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "execution_ms": result.execution_ms,
        "truncated": result.truncated,
        "blocked": result.blocked,
        "block_reason": result.block_reason,
        "formatted": format_sandbox_result(result),
    }


@router.post("/run")
async def api_run_code(req: RunRequest):
    if len(req.code) > 10_000:
        raise HTTPException(status_code=400, detail="Code too long (max 10,000 chars)")
    result = await execute_code(req.code, req.language)
    return _result_response(result)


@router.post("/bash", summary="Run a shell command in a restricted sandbox")
async def api_run_bash(req: BashRequest):
    """
    Execute a shell command safely — ports Claude Code's Bash tool.

    Restrictions:
    - Runs under /tmp with a locked-down PATH
    - Blocked: rm -rf /, sudo, mkfs, dd on devices, fork bombs, curl|bash, eval
    - Timeout: 1–30 seconds (default 15)
    - Output capped at 8,000 chars
    - Interactive programs (vim, less, top) are not supported
    """
    if len(req.command) > 2_000:
        raise HTTPException(status_code=400, detail="Command too long (max 2,000 chars)")
    result = await run_bash(req.command, timeout=req.timeout, env_extras=req.env)
    return _result_response(result)
