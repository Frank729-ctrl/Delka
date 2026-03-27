import asyncio
from fastapi.responses import StreamingResponse
from schemas.support_schema import SupportChatRequest
from services.language_service import detect_language, get_language_instruction
from services.inference_service import generate_stream_response as _inference_stream
from services.output_validator import validate_support_response
from prompts.support_prompt import build_support_system_prompt
from sessions.chat_session_store import get_history, append_message

_FALLBACK = "I'm here to help. Could you rephrase your question?"
_CHUNK_SIZE = 4  # characters per SSE token when fake-streaming


async def handle_chat(data: SupportChatRequest) -> StreamingResponse:
    session_id = data.session_id or "anon"

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
