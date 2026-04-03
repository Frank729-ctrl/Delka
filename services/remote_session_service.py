"""
Remote Session Manager — ports Claude Code's RemoteTrigger concept.

Accepts an inbound webhook POST with a prompt/task, runs it through the
inference chain in the background, and POSTs the result back to the
caller's callback_url when done.

Flow:
  Client → POST /v1/remote/trigger  (prompt + callback_url + session_id)
           → 202 Accepted  { session_id, status: "queued" }
  Server → runs inference async
  Server → POST callback_url  { session_id, status, result, error }

Sessions are in-memory (same TTL model as task_manager_service).
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import httpx

_SESSIONS: dict[str, "RemoteSession"] = {}
_CALLBACK_TIMEOUT = 10   # seconds to wait for callback delivery
_INFERENCE_TIMEOUT = 60  # seconds max for the LLM call


@dataclass
class RemoteSession:
    session_id: str
    prompt: str
    system_prompt: str
    callback_url: Optional[str]
    status: str                    # queued | running | completed | failed
    result: str = ""
    error: str = ""
    provider: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "provider": self.provider,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }


async def _deliver_callback(session: RemoteSession) -> None:
    """POST result to callback_url. Silently swallows delivery errors."""
    if not session.callback_url:
        return
    payload = session.to_dict()
    try:
        async with httpx.AsyncClient(timeout=_CALLBACK_TIMEOUT) as client:
            await client.post(session.callback_url, json=payload)
    except Exception:
        pass   # callback failure doesn't affect session state


async def _run_session(session: RemoteSession) -> None:
    """Execute the prompt and deliver result."""
    session.status = "running"
    try:
        from services.inference_service import generate_full_response
        result, provider, model = await asyncio.wait_for(
            generate_full_response(
                task="chat",
                system_prompt=session.system_prompt or "You are a helpful AI assistant.",
                user_prompt=session.prompt,
                temperature=0.7,
                max_tokens=2000,
            ),
            timeout=_INFERENCE_TIMEOUT,
        )
        session.result = result
        session.provider = provider
        session.status = "completed"
    except asyncio.TimeoutError:
        session.error = f"Inference timed out after {_INFERENCE_TIMEOUT}s"
        session.status = "failed"
    except Exception as exc:
        session.error = str(exc)[:300]
        session.status = "failed"
    finally:
        session.completed_at = time.time()
        await _deliver_callback(session)


def trigger(
    prompt: str,
    callback_url: Optional[str] = None,
    system_prompt: str = "",
    session_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> RemoteSession:
    """
    Queue a remote inference session.
    Returns immediately with status='queued'; runs in background.
    """
    sid = session_id or str(uuid.uuid4())
    session = RemoteSession(
        session_id=sid,
        prompt=prompt,
        system_prompt=system_prompt,
        callback_url=callback_url,
        status="queued",
        metadata=metadata or {},
    )
    _SESSIONS[sid] = session
    asyncio.create_task(_run_session(session))
    return session


def get_session(session_id: str) -> Optional[RemoteSession]:
    return _SESSIONS.get(session_id)


def list_sessions(limit: int = 50) -> list[RemoteSession]:
    sessions = sorted(_SESSIONS.values(), key=lambda s: s.created_at, reverse=True)
    return sessions[:limit]


def purge_old(max_age_seconds: int = 3600) -> int:
    cutoff = time.time() - max_age_seconds
    to_remove = [
        sid for sid, s in _SESSIONS.items()
        if s.status in ("completed", "failed")
        and (s.completed_at or 0) < cutoff
    ]
    for sid in to_remove:
        del _SESSIONS[sid]
    return len(to_remove)
