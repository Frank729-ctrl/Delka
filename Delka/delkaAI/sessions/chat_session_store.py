from datetime import datetime

_sessions: dict[str, list[dict]] = {}

_MAX_HISTORY = 20


def get_history(session_id: str) -> list[dict]:
    return list(_sessions.get(session_id, []))


def append_message(session_id: str, role: str, content: str) -> None:
    if session_id not in _sessions:
        _sessions[session_id] = []
    _sessions[session_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
    })
    # Cap history to avoid unbounded memory growth
    if len(_sessions[session_id]) > _MAX_HISTORY:
        _sessions[session_id] = _sessions[session_id][-_MAX_HISTORY:]


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def get_session_length(session_id: str) -> int:
    return len(_sessions.get(session_id, []))
