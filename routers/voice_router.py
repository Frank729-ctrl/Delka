"""
Voice router — full duplex voice pipeline.

POST   /v1/voice/sessions              — create voice session
GET    /v1/voice/sessions/{id}         — session stats
DELETE /v1/voice/sessions/{id}         — close session
POST   /v1/voice/chat                  — full round trip (audio → text + audio)
POST   /v1/voice/chat/stream           — streaming SSE version (transcript + tokens + audio_ready)
GET    /v1/voice/audio/{session_id}    — fetch TTS audio for last turn
POST   /v1/voice/transcribe            — STT only (enhanced, with keyterms)
GET    /v1/voice/keyterms              — list Ghana-context keyterms
"""
import base64
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.voice_session_service import (
    create_session, get_session, close_session,
    list_sessions, session_stats, push_audio_chunk,
)
from services.voice_chat_service import voice_chat, voice_chat_stream
from services.speech_service import transcribe
from services.voice_keyterms_service import get_keyterms

router = APIRouter(prefix="/v1/voice")


# ── Session management ────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    user_id: str
    platform: str
    language: str = "en"
    voice: str = "en-GH-AmaNewscast"   # TTS voice


@router.post("/sessions")
async def api_create_session(req: CreateSessionRequest):
    session = create_session(req.user_id, req.platform, req.language, req.voice)
    return {
        "status": "ok",
        "session_id": session.session_id,
        "language": session.language,
        "voice": session.voice,
    }


@router.get("/sessions/{session_id}")
async def api_session_stats(session_id: str):
    stats = session_stats(session_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok", **stats}


@router.delete("/sessions/{session_id}")
async def api_close_session(session_id: str):
    close_session(session_id)
    return {"status": "ok", "closed": session_id}


# ── Full voice chat (single round trip) ───────────────────────────────────────

class VoiceChatRequest(BaseModel):
    audio_base64: str
    audio_format: str = "mp3"
    session_id: str = ""
    user_id: str = ""
    platform: str = ""
    language: str = "en"
    voice: str = "en-GH-AmaNewscast"
    return_audio: bool = True    # False = text only (cheaper, faster)


@router.post("/chat")
async def api_voice_chat(req: VoiceChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Full voice pipeline: audio → STT → LLM → TTS.
    Returns transcript, response text, and audio (base64) in one response.
    """
    try:
        audio_bytes = base64.b64decode(req.audio_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 audio")

    result = await voice_chat(
        audio_bytes=audio_bytes,
        audio_format=req.audio_format,
        session_id=req.session_id,
        user_id=req.user_id,
        platform=req.platform,
        language=req.language,
        tts_voice=req.voice,
        db=db,
    )

    response = {
        "status": "ok",
        "transcript": result.transcript,
        "stt_provider": result.stt_provider,
        "stt_confidence": result.stt_confidence,
        "language": result.language,
        "response_text": result.response_text,
        "llm_provider": result.llm_provider,
        "tts_provider": result.tts_provider,
        "timing": {
            "stt_ms": result.stt_ms,
            "llm_ms": result.llm_ms,
            "tts_ms": result.tts_ms,
            "total_ms": result.total_ms,
        },
        "low_confidence": result.low_confidence,
        "clarification_needed": result.clarification_needed,
    }

    if req.return_audio and result.audio_bytes:
        response["audio_base64"] = base64.b64encode(result.audio_bytes).decode()
        response["audio_content_type"] = result.audio_content_type

    return response


@router.post("/chat/stream")
async def api_voice_chat_stream(req: VoiceChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Streaming voice chat via SSE.
    Events: transcript → tokens (LLM) → audio_ready → done
    Fetch audio separately from /v1/voice/audio/{session_id}
    """
    try:
        audio_bytes = base64.b64decode(req.audio_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 audio")

    return StreamingResponse(
        voice_chat_stream(
            audio_bytes=audio_bytes,
            audio_format=req.audio_format,
            session_id=req.session_id,
            user_id=req.user_id,
            platform=req.platform,
            language=req.language,
            tts_voice=req.voice,
            db=db,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/audio/{session_id}")
async def api_get_audio(session_id: str):
    """Return the TTS audio for the last voice turn."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.pending_audio:
        raise HTTPException(status_code=404, detail="No audio ready")
    return Response(
        content=session.pending_audio,
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=response.mp3"},
    )


# ── STT only (enhanced) ───────────────────────────────────────────────────────

class TranscribeRequest(BaseModel):
    audio_base64: str = ""
    audio_url: str = ""
    audio_format: str = "mp3"
    language: str = "en"
    context: str = ""   # recent conversation for keyterm biasing


@router.post("/transcribe")
async def api_transcribe(req: TranscribeRequest):
    if not req.audio_base64 and not req.audio_url:
        raise HTTPException(status_code=400, detail="Provide audio_base64 or audio_url")

    result = await transcribe(
        audio_url=req.audio_url,
        audio_base64=req.audio_base64,
        language=req.language,
        audio_format=req.audio_format,
        context=req.context,
    )

    if result.provider == "unavailable":
        raise HTTPException(status_code=503, detail="STT unavailable. Check GROQ_API_KEY.")

    return {
        "status": "ok",
        "transcript": result.text,
        "language": result.language,
        "confidence": result.confidence,
        "word_count": result.word_count,
        "provider": result.provider,
        "duration_ms": result.duration_ms,
    }


# ── Keyterms ──────────────────────────────────────────────────────────────────

@router.get("/keyterms")
async def api_keyterms(platform: str = "", context: str = ""):
    terms = get_keyterms(platform=platform, context=context)
    return {"status": "ok", "count": len(terms), "keyterms": terms}
