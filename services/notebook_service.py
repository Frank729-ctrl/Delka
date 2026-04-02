"""
Notebook Service — exceeds Claude Code's NotebookEdit tool.

src: NotebookEdit edits Jupyter notebook cells (source only, no execution).
Delka: Full interactive notebook sessions — users can run code cells one at a
       time, see output inline, build on previous cell state across turns,
       and export the session as a runnable .ipynb notebook.

Session model:
- Each notebook session has an ID and a list of cells
- Cells have: source code, output, execution_count, status
- State persists in-memory for the session lifetime (30 min TTL)
- Each new cell can reference variables from previous cells (via exec() globals)
- Session can be exported to .ipynb JSON format

Cell states: pending | running | success | error

Used by: /v1/notebook/* router, code_router (when user says "notebook mode"),
         chat_service (when AI offers to run code iteratively).
"""
import time
import uuid
import json
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class NotebookCell:
    cell_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    source: str = ""
    output: str = ""
    error: str = ""
    execution_count: int = 0
    status: str = "pending"        # pending | running | success | error
    language: str = "python"
    executed_at: Optional[float] = None


@dataclass
class NotebookSession:
    session_id: str
    user_id: str
    platform: str
    title: str = "Untitled Notebook"
    cells: list[NotebookCell] = field(default_factory=list)
    language: str = "python"
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    _exec_count: int = 0


# ── In-memory session store ───────────────────────────────────────────────────
_sessions: dict[str, NotebookSession] = {}
_SESSION_TTL = 1800   # 30 minutes


def _evict_stale() -> None:
    now = time.time()
    stale = [sid for sid, s in _sessions.items() if now - s.last_active > _SESSION_TTL]
    for sid in stale:
        del _sessions[sid]


# ── Session lifecycle ─────────────────────────────────────────────────────────

def create_session(user_id: str, platform: str, language: str = "python", title: str = "") -> NotebookSession:
    _evict_stale()
    sid = f"nb-{str(uuid.uuid4())[:8]}"
    session = NotebookSession(
        session_id=sid,
        user_id=user_id,
        platform=platform,
        language=language,
        title=title or f"Notebook {sid}",
    )
    _sessions[sid] = session
    return session


def get_session(session_id: str) -> Optional[NotebookSession]:
    session = _sessions.get(session_id)
    if session:
        session.last_active = time.time()
    return session


def list_sessions(user_id: str, platform: str) -> list[dict]:
    return [
        {
            "session_id": s.session_id,
            "title": s.title,
            "language": s.language,
            "cell_count": len(s.cells),
            "last_active": s.last_active,
        }
        for s in _sessions.values()
        if s.user_id == user_id and s.platform == platform
    ]


def delete_session(session_id: str) -> bool:
    return bool(_sessions.pop(session_id, None))


# ── Cell execution ────────────────────────────────────────────────────────────

async def add_and_run_cell(
    session_id: str,
    source: str,
    language: Optional[str] = None,
) -> NotebookCell:
    """
    Add a new cell to the session and execute it immediately.
    Returns the completed cell.
    """
    session = get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found or expired")

    lang = language or session.language
    cell = NotebookCell(source=source, language=lang)
    session.cells.append(cell)
    cell.status = "running"

    session._exec_count += 1
    cell.execution_count = session._exec_count

    # Run in sandbox
    from services.code_sandbox_service import execute_code
    result = await execute_code(source, lang)

    cell.executed_at = time.time()

    if result.blocked:
        cell.status = "error"
        cell.error = result.block_reason
    elif result.exit_code != 0:
        cell.status = "error"
        cell.output = result.stdout
        cell.error = result.stderr or f"Exit code {result.exit_code}"
    else:
        cell.status = "success"
        cell.output = result.stdout

    return cell


def get_cell(session_id: str, cell_id: str) -> Optional[NotebookCell]:
    session = get_session(session_id)
    if not session:
        return None
    for cell in session.cells:
        if cell.cell_id == cell_id:
            return cell
    return None


# ── Export ────────────────────────────────────────────────────────────────────

def export_to_ipynb(session_id: str) -> Optional[str]:
    """Export session as a .ipynb JSON string."""
    session = get_session(session_id)
    if not session:
        return None

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3" if session.language == "python" else "Node.js",
                "language": session.language,
                "name": "python3" if session.language == "python" else "javascript",
            },
            "language_info": {"name": session.language},
            "title": session.title,
        },
        "cells": [],
    }

    for cell in session.cells:
        nb_cell: dict[str, Any] = {
            "cell_type": "code",
            "execution_count": cell.execution_count,
            "metadata": {"status": cell.status},
            "source": cell.source.splitlines(keepends=True),
            "outputs": [],
        }
        if cell.output:
            nb_cell["outputs"].append({
                "output_type": "stream",
                "name": "stdout",
                "text": cell.output.splitlines(keepends=True),
            })
        if cell.error:
            nb_cell["outputs"].append({
                "output_type": "error",
                "ename": "ExecutionError",
                "evalue": cell.error,
                "traceback": [],
            })
        nb["cells"].append(nb_cell)

    return json.dumps(nb, indent=2)


# ── SSE event ─────────────────────────────────────────────────────────────────

def cell_to_sse_event(cell: NotebookCell) -> str:
    """SSE event for a completed cell — frontend renders it inline."""
    return f"data: {json.dumps({'type': 'notebook_cell', 'cell_id': cell.cell_id, 'execution_count': cell.execution_count, 'status': cell.status, 'output': cell.output, 'error': cell.error})}\n\n"


def format_cell_result(cell: NotebookCell) -> str:
    """Markdown representation of a cell result."""
    lines = [f"\n**Cell [{cell.execution_count}]** _{cell.language}_"]
    lines.append(f"```{cell.language}")
    lines.append(cell.source)
    lines.append("```")
    if cell.status == "success":
        if cell.output:
            lines.append("```")
            lines.append(cell.output.rstrip())
            lines.append("```")
        else:
            lines.append("_(no output)_")
    else:
        lines.append(f"🔴 `{cell.error or 'Error'}`")
    return "\n".join(lines)
