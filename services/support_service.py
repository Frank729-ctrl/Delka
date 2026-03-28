import asyncio
import time
from fastapi.responses import StreamingResponse
from schemas.support_schema import SupportChatRequest
from services.language_service import detect_language, get_language_instruction
from services.inference_service import generate_stream_response as _inference_stream
from services.output_validator import validate_support_response
from prompts.support_prompt import build_support_system_prompt
from sessions.chat_session_store import get_history, append_message

_FALLBACK = "I'm here to help. Could you rephrase your question?"
_CHUNK_SIZE = 4  # characters per SSE token when fake-streaming


async def get_plain_reply(
    message: str,
    session_id: str,
    user_id: str,
    platform: str,
    db=None,
) -> tuple[str, str]:
    """Return (reply_text, session_id) without streaming — used by non-SSE callers."""
    data = SupportChatRequest(
        message=message,
        platform=platform,
        session_id=session_id,
        user_id=user_id,
    )
    sid = data.session_id or "anon"

    lang = detect_language(data.message)
    lang_instruction = get_language_instruction(lang)
    system_prompt = build_support_system_prompt(data.platform, lang_instruction)

    history = get_history(sid)
    messages = [{"role": "system", "content": system_prompt}]
    for entry in history:
        messages.append({"role": entry["role"], "content": entry["content"]})
    messages.append({"role": "user", "content": data.message})

    tokens: list[str] = []
    async for token in _inference_stream("support", messages):
        tokens.append(token)

    full_response = "".join(tokens)
    if not validate_support_response(full_response):
        full_response = _FALLBACK

    append_message(sid, "user", data.message)
    append_message(sid, "assistant", full_response)

    return full_response, sid


async def handle_chat(data: SupportChatRequest, db=None) -> StreamingResponse:
    session_id = data.session_id or "anon"
    start_ms = int(time.time() * 1000)

    lang = detect_language(data.message)
    lang_instruction = get_language_instruction(lang)
    system_prompt = build_support_system_prompt(data.platform, lang_instruction)

    history = get_history(session_id)
    messages = [{"role": "system", "content": system_prompt}]
    for entry in history:
        messages.append({"role": entry["role"], "content": entry["content"]})
    messages.append({"role": "user", "content": data.message})

    # Collect full response then validate before streaming
    tokens: list[str] = []
    async for token in _inference_stream("support", messages):
        tokens.append(token)

    full_response = "".join(tokens)

    if not validate_support_response(full_response):
        full_response = _FALLBACK

    append_message(session_id, "user", data.message)
    append_message(session_id, "assistant", full_response)

    # Memory hooks — only when user_id provided and db available
    if db is not None and data.user_id:
        try:
            response_ms = int(time.time() * 1000) - start_ms
            from services import conversation_history_service, feedback_service
            from services.memory_service import extract_profile_updates, get_or_create_profile, update_profile

            profile = await get_or_create_profile(data.user_id, data.platform, db)
            await conversation_history_service.store_message(
                data.user_id, data.platform, session_id, "user", data.message, db
            )
            await conversation_history_service.store_message(
                data.user_id, data.platform, session_id, "assistant", full_response, db
            )
            await feedback_service.store_feedback_log(
                user_id=data.user_id,
                platform=data.platform,
                session_id=session_id,
                service="support",
                request_data={"message": data.message},
                response_data={"response": full_response[:500]},
                provider_used="groq",
                model_used="",
                response_ms=response_ms,
                db=db,
            )
            updates = await extract_profile_updates(data.message, full_response, profile)
            await update_profile(data.user_id, data.platform, updates, db)
        except Exception:
            pass  # Memory failures never break chat

    async def sse_generator():
        for i in range(0, len(full_response), _CHUNK_SIZE):
            chunk = full_response[i : i + _CHUNK_SIZE]
            yield f"data: {chunk}\n\n"
            await asyncio.sleep(0)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
