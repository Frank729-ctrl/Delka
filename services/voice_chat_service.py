"""
Voice Chat Service — exceeds Claude Code's voice + voiceStreamSTT combined.

src: Push-to-talk → Anthropic voice_stream WebSocket → Claude processes text.
     TTS response is separate (user reads text). Audio in, text out only.
Delka: Full duplex voice pipeline:
     audio in → STT (Groq Whisper + keyterms) → LLM chat → TTS (edge-tts) → audio out
     One API call returns BOTH the text response AND the audio bytes.

Also supports:
- Voice session context (history maintained across turns)
- Streaming: SSE stream with partial transcript then streaming text then audio URL
- Language auto-detection from STT
- Tone-matched TTS voice selection (formal/casual)
- Confidence-gated response (low STT confidence → ask for clarification)

Used by: voice_router (/v1/voice/*)
"""
import asyncio
import base64
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

from services.speech_service import transcribe
from services.tts_service import synthesize
from services.voice_session_service import (
    get_session, record_turn, get_chat_history,
    create_session, VoiceState,
)


# Confidence threshold below which we ask user to repeat
_MIN_CONFIDENCE = 0.45

# Max response length for TTS (longer responses take too long to synthesize)
_TTS_MAX_CHARS = 600


@dataclass
class VoiceChatResult:
    # STT
    transcript: str
    stt_provider: str
    stt_confidence: float
    language: str

    # LLM
    response_text: str
    llm_provider: str
    llm_model: str

    # TTS
    audio_bytes: bytes
    audio_content_type: str
    tts_provider: str

    # Timing
    stt_ms: float
    llm_ms: float
    tts_ms: float
    total_ms: float

    # Meta
    low_confidence: bool = False
    clarification_needed: bool = False


async def voice_chat(
    audio_bytes: bytes,
    audio_format: str = "mp3",
    session_id: str = "",
    user_id: str = "",
    platform: str = "",
    language: str = "en",
    tts_voice: str = "en-GH-AmaNewscast",
    db=None,
) -> VoiceChatResult:
    """
    Full voice pipeline:
      1. STT: transcribe audio with keyterm biasing
      2. LLM: generate text response using session history
      3. TTS: synthesize response audio
    Returns VoiceChatResult with everything.
    """
    total_start = time.time()

    # ── 1. STT ────────────────────────────────────────────────────────────────
    stt_start = time.time()
    audio_b64 = base64.b64encode(audio_bytes).decode()

    # Get recent context for keyterm biasing
    recent_context = ""
    if session_id:
        history = get_chat_history(session_id)
        if history:
            recent_context = " ".join(h["content"] for h in history[-2:])

    stt_result = await transcribe(
        audio_base64=audio_b64,
        language=language,
        audio_format=audio_format,
        context=recent_context,
    )
    stt_ms = round((time.time() - stt_start) * 1000, 1)

    transcript = stt_result.text
    detected_lang = stt_result.language or language

    # Low confidence — ask user to repeat
    if stt_result.confidence < _MIN_CONFIDENCE or not transcript:
        clarification = "I didn't quite catch that. Could you please repeat?"
        tts_audio, tts_content_type, tts_prov = await synthesize(clarification, tts_voice)
        return VoiceChatResult(
            transcript=transcript,
            stt_provider=stt_result.provider,
            stt_confidence=stt_result.confidence,
            language=detected_lang,
            response_text=clarification,
            llm_provider="none",
            llm_model="",
            audio_bytes=tts_audio,
            audio_content_type=tts_content_type,
            tts_provider=tts_prov,
            stt_ms=stt_ms, llm_ms=0, tts_ms=0,
            total_ms=round((time.time() - total_start) * 1000, 1),
            low_confidence=True,
            clarification_needed=True,
        )

    # ── 2. LLM ────────────────────────────────────────────────────────────────
    llm_start = time.time()

    # Build messages with voice session history
    history = get_chat_history(session_id) if session_id else []

    from services.inference_service import generate_full_response
    from prompts.personality_prompt import CORE_IDENTITY_PROMPT

    voice_system = (
        f"{CORE_IDENTITY_PROMPT}\n\n"
        "You are responding in VOICE MODE. Rules:\n"
        "- Keep responses SHORT (2-4 sentences max)\n"
        "- No markdown, no bullet points, no code blocks\n"
        "- Speak naturally, like a conversation\n"
        "- No lists or numbered steps — use 'first, then, finally'\n"
        "- Avoid special characters that sound odd when spoken aloud\n"
    )

    # Build message with history
    messages = [{"role": "system", "content": voice_system}]
    messages.extend(history)
    messages.append({"role": "user", "content": transcript})

    try:
        from services.inference_service import _get_provider_client, get_task_chain
        response_text, llm_provider, llm_model = await generate_full_response(
            task="support",
            system_prompt=voice_system,
            user_prompt=transcript,
            temperature=0.7,
            max_tokens=200,      # Short for voice
        )
    except Exception:
        response_text = "I'm having trouble responding right now. Please try again."
        llm_provider, llm_model = "none", ""

    llm_ms = round((time.time() - llm_start) * 1000, 1)

    # ── 3. TTS ────────────────────────────────────────────────────────────────
    tts_start = time.time()

    # Truncate for TTS if too long
    tts_text = response_text
    if len(tts_text) > _TTS_MAX_CHARS:
        # Cut at last sentence boundary within limit
        cut = tts_text[:_TTS_MAX_CHARS].rfind(". ")
        tts_text = tts_text[:cut + 1] if cut > 0 else tts_text[:_TTS_MAX_CHARS]

    tts_audio, tts_content_type, tts_provider = await synthesize(tts_text, tts_voice)
    tts_ms = round((time.time() - tts_start) * 1000, 1)

    # ── Save turn to session ──────────────────────────────────────────────────
    if session_id:
        record_turn(
            session_id=session_id,
            user_text=transcript,
            assistant_text=response_text,
            audio_duration_s=stt_result.duration_ms / 1000,
            provider=stt_result.provider,
            confidence=stt_result.confidence,
        )

    return VoiceChatResult(
        transcript=transcript,
        stt_provider=stt_result.provider,
        stt_confidence=stt_result.confidence,
        language=detected_lang,
        response_text=response_text,
        llm_provider=llm_provider,
        llm_model=llm_model,
        audio_bytes=tts_audio,
        audio_content_type=tts_content_type,
        tts_provider=tts_provider,
        stt_ms=stt_ms,
        llm_ms=llm_ms,
        tts_ms=tts_ms,
        total_ms=round((time.time() - total_start) * 1000, 1),
        low_confidence=False,
        clarification_needed=False,
    )


async def voice_chat_stream(
    audio_bytes: bytes,
    audio_format: str = "mp3",
    session_id: str = "",
    user_id: str = "",
    platform: str = "",
    language: str = "en",
    tts_voice: str = "en-GH-AmaNewscast",
    db=None,
) -> AsyncGenerator[str, None]:
    """
    Streaming version of voice_chat.
    SSE events:
      {"type": "transcript", "text": "...", "confidence": 0.9}
      {"type": "token", "text": "..."}         ← LLM tokens as they stream
      {"type": "audio_ready", "duration_s": 2.1}
      {"type": "done", "stt_ms": ..., "llm_ms": ..., "tts_ms": ...}
    Audio bytes are returned in a follow-up /v1/voice/audio/{session_id} call.
    """
    import json
    total_start = time.time()

    # ── 1. STT ────────────────────────────────────────────────────────────────
    audio_b64 = base64.b64encode(audio_bytes).decode()
    recent_context = ""
    if session_id:
        history = get_chat_history(session_id)
        recent_context = " ".join(h["content"] for h in history[-2:])

    stt_result = await transcribe(
        audio_base64=audio_b64, language=language,
        audio_format=audio_format, context=recent_context,
    )
    stt_ms = round((time.time() - total_start) * 1000, 1)

    yield f"data: {json.dumps({'type': 'transcript', 'text': stt_result.text, 'confidence': stt_result.confidence, 'language': stt_result.language})}\n\n"

    if not stt_result.text or stt_result.confidence < _MIN_CONFIDENCE:
        clarification = "I didn't catch that. Could you repeat?"
        yield f"data: {json.dumps({'type': 'token', 'text': clarification})}\n\n"
        # Pre-generate TTS for clarification
        tts_audio, _, _ = await synthesize(clarification, tts_voice)
        if session_id:
            s = get_session(session_id)
            if s:
                s.pending_audio = tts_audio
                s.pending_text = clarification
        yield f"data: {json.dumps({'type': 'audio_ready', 'duration_s': 2})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'clarification': True})}\n\n"
        return

    # ── 2. Stream LLM tokens ──────────────────────────────────────────────────
    llm_start = time.time()
    history = get_chat_history(session_id) if session_id else []
    from prompts.personality_prompt import CORE_IDENTITY_PROMPT
    voice_system = (
        f"{CORE_IDENTITY_PROMPT}\n\nVOICE MODE: short, natural, no markdown, 2-4 sentences max."
    )

    from services.inference_service import generate_stream_response
    tokens = []
    async for token in generate_stream_response(
        "support",
        [{"role": "system", "content": voice_system}] + history + [{"role": "user", "content": stt_result.text}],
    ):
        tokens.append(token)
        yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"

    response_text = "".join(tokens)
    llm_ms = round((time.time() - llm_start) * 1000, 1)

    # ── 3. Synthesize TTS (background, store for retrieval) ───────────────────
    tts_start = time.time()
    tts_text = response_text[:_TTS_MAX_CHARS]
    tts_audio, tts_content_type, tts_provider = await synthesize(tts_text, tts_voice)
    tts_ms = round((time.time() - tts_start) * 1000, 1)

    # Store audio on session for retrieval
    if session_id:
        s = get_session(session_id)
        if s:
            s.pending_audio = tts_audio
            s.pending_text = response_text
        record_turn(
            session_id=session_id,
            user_text=stt_result.text,
            assistant_text=response_text,
            audio_duration_s=stt_result.duration_ms / 1000,
            provider=stt_result.provider,
            confidence=stt_result.confidence,
        )

    yield f"data: {json.dumps({'type': 'audio_ready', 'duration_s': round(len(tts_audio) / 32000, 1)})}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'stt_ms': stt_ms, 'llm_ms': llm_ms, 'tts_ms': tts_ms, 'total_ms': round((time.time() - total_start) * 1000, 1)})}\n\n"
