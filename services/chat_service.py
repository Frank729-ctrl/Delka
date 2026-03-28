import time
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.chat_schema import ChatRequest
from services.language_service import detect_language, get_language_instruction
from services.inference_service import generate_stream_response as _inference_stream
from services import memory_service, conversation_history_service, feedback_service
from services.personality_service import analyze_user_tone
from services.correction_service import extract_and_store_correction
from services.search_service import needs_search, extract_search_query, search
from prompts.chat_prompt import build_chat_system_prompt

_CHUNK_SIZE = 4


async def chat(
    request: ChatRequest,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    user_id = request.user_id
    platform = request.platform
    session_id = request.session_id or f"chat-{int(time.time())}"

    # 1. Fetch memory
    profile = await memory_service.get_or_create_profile(user_id, platform, db)
    recent_history = await conversation_history_service.get_recent_history(
        user_id, platform, db
    )
    rag_examples = await feedback_service.get_rag_examples(
        user_id, platform, "chat", db
    )

    # 2. Language + tone
    lang = detect_language(request.message)
    language_instruction = get_language_instruction(lang)
    tone_analysis = analyze_user_tone(request.message)

    # 3. Correction detection — short-circuit if correction found
    correction_ack = await extract_and_store_correction(
        request.message, user_id, platform, db
    )
    if correction_ack:
        await conversation_history_service.store_message(
            user_id, platform, session_id, "user", request.message, db
        )
        await conversation_history_service.store_message(
            user_id, platform, session_id, "assistant", correction_ack, db
        )
        yield f"data: {correction_ack}\n\n"
        yield "data: [DONE]\n\n"
        return

    # 3b. Web search (Tavily) — fetch context before building system prompt
    search_context = ""
    if needs_search(request.message):
        query = extract_search_query(request.message)
        search_context = await search(query)

    # 4. Build system prompt
    system_prompt = build_chat_system_prompt(
        platform=platform,
        profile=profile,
        recent_history=recent_history,
        rag_examples=rag_examples,
        tone_analysis=tone_analysis,
        language_instruction=language_instruction,
    )
    if search_context:
        system_prompt = f"{system_prompt}\n\n{search_context}"

    # 5. Build messages
    messages = [{"role": "system", "content": system_prompt}]
    for entry in recent_history:
        if entry["role"] in ("user", "assistant"):
            messages.append({"role": entry["role"], "content": entry["content"]})
    messages.append({"role": "user", "content": request.message})

    # 6. Stream from inference
    tokens: list[str] = []
    async for token in _inference_stream("chat", messages):
        tokens.append(token)
        yield f"data: {token}\n\n"

    full_response = "".join(tokens)
    yield "data: [DONE]\n\n"

    # 7-10. Post-stream persistence — wrapped so a session edge case never surfaces to the client
    try:
        await conversation_history_service.store_message(
            user_id, platform, session_id, "user", request.message, db
        )
        await conversation_history_service.store_message(
            user_id, platform, session_id, "assistant", full_response, db
        )
        updates = await memory_service.extract_profile_updates(
            request.message, full_response, profile
        )
        await memory_service.update_profile(user_id, platform, updates, db)
        await feedback_service.store_feedback_log(
            user_id=user_id,
            platform=platform,
            session_id=session_id,
            service="chat",
            request_data={"message": request.message},
            response_data={"response": full_response[:500]},
            provider_used="groq",
            model_used="",
            response_ms=0,
            db=db,
        )
        await conversation_history_service.summarize_old_history(user_id, platform, db)
    except Exception:
        pass
