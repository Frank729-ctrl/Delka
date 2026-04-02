"""
Code sandbox router — execute code snippets directly.

POST /v1/code/run  — execute Python or JavaScript, return output
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.code_sandbox_service import execute_code, format_sandbox_result

router = APIRouter(prefix="/v1/code")


class RunRequest(BaseModel):
    code: str
    language: str = "python"   # "python" | "javascript"


@router.post("/run")
async def api_run_code(req: RunRequest):
    if len(req.code) > 10_000:
        raise HTTPException(status_code=400, detail="Code too long (max 10,000 chars)")

    result = await execute_code(req.code, req.language)

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
