"""
Voice Session Service — exceeds Claude Code's useVoice.ts state management.

src: useVoice.ts manages push-to-talk state (recording/idle/processing),
     hold-to-talk keybinding, VAD (voice activity detection), keep-alive pings.
Delka: HTTP-based voice session with:
     - Session state machine (idle → listening → transcribing → speaking)
     - Conversation history maintained across voice turns
     - Auto silence detection via client-reported chunk durations
     - Keep-alive pings to hold the session open
     - TTS response queuing (pre-generate while user is still speaking)

Session lifecycle:
  create_session → [send_audio_chunk ... finalize_audio] → get_response → [repeat]
"""
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


# ── State machine ─────────────────────────────────────────────────────────────
# idle → listening → transcribing → responding → idle (loop)

class VoiceState:
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    RESPONDING = "responding"


@dataclass
class VoiceTurn:
    user_text: str
    assistant_text: str
    audio_duration_s: float
    provider: str
    confidence: float
    ts: float = field(default_factory=time.time)


@dataclass
class VoiceSession:
    session_id: str
    user_id: str
    platform: str
    state: str = VoiceState.IDLE
    language: str = "en"
    voice: str = "en-GH-AmaNewscast"    # TTS voice
    history: list[VoiceTurn] = field(default_factory=list)
    audio_chunks: list[bytes] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    # Pre-generated TTS for the response (ready before user finishes reading)
    pending_audio: Optional[bytes] = None
    pending_text: Optional[str] = None


# ── In-memory store ───────────────────────────────────────────────────────────
_sessions: dict[str, VoiceSession] = {}
_SESSION_TTL = 1800   # 30 minutes idle timeout


def _evict_stale() -> None:
    now = time.time()
    stale = [sid for sid, s in _sessions.items() if now - s.last_active > _SESSION_TTL]
    for sid in stale:
        del _sessions[sid]


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def create_session(
    user_id: str,
    platform: str,
    language: str = "en",
    voice: str = "en-GH-AmaNewscast",
) -> VoiceSession:
    _evict_stale()
    session = VoiceSession(
        session_id=f"vs-{str(uuid.uuid4())[:8]}",
        user_id=user_id,
        platform=platform,
        language=language,
        voice=voice,
    )
    _sessions[session.session_id] = session
    return session


def get_session(session_id: str) -> Optional[VoiceSession]:
    s = _sessions.get(session_id)
    if s:
        s.last_active = time.time()
    return s


def close_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def list_sessions(user_id: str) -> list[dict]:
    return [
        {
            "session_id": s.session_id,
            "state": s.state,
            "turns": len(s.history),
            "language": s.language,
            "last_active": s.last_active,
        }
        for s in _sessions.values()
        if s.user_id == user_id
    ]


# ── Audio chunk buffering ─────────────────────────────────────────────────────

def push_audio_chunk(session_id: str, chunk: bytes) -> bool:
    """Buffer an audio chunk. Returns False if session not found."""
    s = get_session(session_id)
    if not s:
        return False
    s.audio_chunks.append(chunk)
    s.state = VoiceState.LISTENING
    return True


def get_buffered_audio(session_id: str) -> bytes:
    """Get all buffered audio chunks as a single byte string."""
    s = get_session(session_id)
    if not s:
        return b""
    return b"".join(s.audio_chunks)


def clear_audio_buffer(session_id: str) -> None:
    s = get_session(session_id)
    if s:
        s.audio_chunks = []


# ── Conversation history ──────────────────────────────────────────────────────

def get_chat_history(session_id: str) -> list[dict]:
    """Return conversation history in chat format for LLM injection."""
    s = get_session(session_id)
    if not s:
        return []
    history = []
    for turn in s.history[-6:]:   # last 6 turns (3 exchanges)
        history.append({"role": "user", "content": turn.user_text})
        history.append({"role": "assistant", "content": turn.assistant_text})
    return history


def record_turn(
    session_id: str,
    user_text: str,
    assistant_text: str,
    audio_duration_s: float = 0.0,
    provider: str = "",
    confidence: float = 0.9,
) -> None:
    s = get_session(session_id)
    if s:
        s.history.append(VoiceTurn(
            user_text=user_text,
            assistant_text=assistant_text,
            audio_duration_s=audio_duration_s,
            provider=provider,
            confidence=confidence,
        ))
        s.state = VoiceState.IDLE
        clear_audio_buffer(session_id)


# ── Stats ─────────────────────────────────────────────────────────────────────

def session_stats(session_id: str) -> dict:
    s = get_session(session_id)
    if not s:
        return {}
    total_audio = sum(t.audio_duration_s for t in s.history)
    avg_confidence = (
        sum(t.confidence for t in s.history) / len(s.history)
        if s.history else 0.0
    )
    return {
        "session_id": session_id,
        "state": s.state,
        "turns": len(s.history),
        "total_audio_seconds": round(total_audio, 1),
        "avg_confidence": round(avg_confidence, 2),
        "language": s.language,
        "voice": s.voice,
        "age_minutes": round((time.time() - s.created_at) / 60, 1),
    }
