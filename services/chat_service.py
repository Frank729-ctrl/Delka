"""
Chat service — the main orchestrator for all chat requests.

Features wired in (inspired by Claude Code src):
1. Token counting + context window awareness
2. Auto-compact when context approaches limit
3. Background session memory extraction (after every reply)
4. AutoDream consolidation (periodic, background)
5. Away summary (if user was gone > 30 min)
6. Prompt suggestions (follow-up question hints)
7. Skills / slash commands (/cv, /summarize, /debug, etc.)
8. MCP agentic tool-use loop
9. Capability routing (image gen, code, translation inline)
10. Coordinator mode for complex multi-part requests
"""
import asyncio
import json
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
from services.plugins.plugin_service import run_plugins
from services.capability_router import route_capability
from services.skills_service import detect_skill, run_skill
from services.coordinator_service import needs_coordinator, run_coordinator
from services.token_counter import should_compact, context_usage_ratio
from prompts.chat_prompt import build_chat_system_prompt

_CHUNK_SIZE = 4


async def _noop() -> str:
    return ""


async def chat(
    request: ChatRequest,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    user_id = request.user_id
    platform = request.platform
    session_id = request.session_id or f"chat-{int(time.time())}"

    # ── 1. Fetch memory ───────────────────────────────────────────────────────
    profile = await memory_service.get_or_create_profile(user_id, platform, db)
    recent_history = await conversation_history_service.get_recent_history(
        user_id, platform, db, session_id=session_id
    )
    rag_examples = await feedback_service.get_rag_examples(
        user_id, platform, "chat", db
    )

    # ── 2. Away summary — if user was gone > 30 min, show recap first ─────────
    from services.away_summary_service import get_away_summary
    away_recap = await get_away_summary(user_id, platform, session_id, db)
    if away_recap and not recent_history:
        # Only show recap at session start (no messages yet this turn)
        yield f"data: {json.dumps({'type': 'away_summary', 'content': away_recap})}\n\n"

    # ── 3. Language + tone ────────────────────────────────────────────────────
    lang = detect_language(request.message)
    language_instruction = get_language_instruction(lang)
    tone_analysis = analyze_user_tone(request.message)

    # ── 4. Correction detection ───────────────────────────────────────────────
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

    # ── 5. Skills / slash commands ────────────────────────────────────────────
    skill_match = detect_skill(request.message)
    if skill_match:
        skill_name, skill_args = skill_match
        result = await run_skill(skill_name, skill_args, platform)
        content = result.get("content", "")
        await conversation_history_service.store_message(
            user_id, platform, session_id, "user", request.message, db
        )
        await conversation_history_service.store_message(
            user_id, platform, session_id, "assistant", content, db
        )
        yield f"data: {json.dumps({'type': result['type'], 'content': content})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # ── 6. Capability routing (image gen, code, translation) ──────────────────
    capability_result = await route_capability(request.message)
    if capability_result:
        await conversation_history_service.store_message(
            user_id, platform, session_id, "user", request.message, db
        )
        await conversation_history_service.store_message(
            user_id, platform, session_id, "assistant", capability_result, db
        )
        yield f"data: {json.dumps({'content': capability_result})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # ── 7. Coordinator mode for complex multi-part requests ───────────────────
    if needs_coordinator(request.message):
        profile_summary = (
            f"Name: {profile.name or 'unknown'}, "
            f"Role: {profile.role or 'unknown'}, "
            f"Notes: {(profile.notes or '')[:200]}"
        )
        coordinator_result = await run_coordinator(
            request.message, profile_summary, platform
        )
        if coordinator_result:
            await conversation_history_service.store_message(
                user_id, platform, session_id, "user", request.message, db
            )
            await conversation_history_service.store_message(
                user_id, platform, session_id, "assistant", coordinator_result, db
            )
            yield f"data: {json.dumps({'type': 'coordinator', 'content': coordinator_result})}\n\n"
            yield "data: [DONE]\n\n"
            # Fire background tasks
            asyncio.create_task(_post_reply_tasks(
                user_id, platform, session_id,
                request.message, coordinator_result,
                recent_history, profile, db
            ))
            return

    # ── 8. Plugins + web search (parallel) ───────────────────────────────────
    context_hint = ""
    for entry in reversed(recent_history):
        if entry["role"] == "user" and len(entry["content"].split()) >= 3:
            context_hint = entry["content"]
            break

    search_task = None
    if needs_search(request.message):
        query = extract_search_query(request.message, context_hint=context_hint)
        search_task = asyncio.create_task(search(query))

    plugin_context, search_context = await asyncio.gather(
        run_plugins(request.message),
        search_task if search_task else _noop(),
    )

    # ── 9. Session memories ───────────────────────────────────────────────────
    from services.session_memory_service import get_memories
    session_memories = await get_memories(user_id, platform, db)

    # ── 10. Build system prompt ───────────────────────────────────────────────
    system_prompt = build_chat_system_prompt(
        platform=platform,
        profile=profile,
        recent_history=recent_history,
        rag_examples=rag_examples,
        tone_analysis=tone_analysis,
        language_instruction=language_instruction,
    )
    if session_memories:
        system_prompt = f"{system_prompt}\n\n{session_memories}"
    if plugin_context:
        system_prompt = f"{system_prompt}\n\n{plugin_context}"
    if search_context:
        system_prompt = f"{system_prompt}\n\n{search_context}"

    # ── 11. Build messages with token awareness ───────────────────────────────
    from services.inference_service import get_task_chain
    chain = get_task_chain("chat")
    current_model = chain[0]["model"] if chain else "llama-3.1-8b-instant"

    messages = [{"role": "system", "content": system_prompt}]
    for entry in recent_history:
        if entry["role"] in ("user", "assistant"):
            messages.append({"role": entry["role"], "content": entry["content"]})
    messages.append({"role": "user", "content": request.message})

    # Auto-compact if context is getting full
    if should_compact(messages, current_model):
        from services.compact_service import maybe_compact
        messages = await maybe_compact(
            user_id, platform, session_id, messages, current_model, db
        )

    # ── 12. Stream from inference ─────────────────────────────────────────────
    tokens: list[str] = []
    async for token in _inference_stream("chat", messages):
        tokens.append(token)
        yield f"data: {token}\n\n"

    full_response = "".join(tokens)

    # Send context usage stats (frontend can show a subtle indicator)
    usage = context_usage_ratio(messages, current_model)
    if usage > 0.6:
        yield f"data: {json.dumps({'type': 'context_usage', 'pct': round(usage * 100)})}\n\n"

    yield "data: [DONE]\n\n"

    # ── 13. Background tasks (non-blocking) ───────────────────────────────────
    asyncio.create_task(_post_reply_tasks(
        user_id, platform, session_id,
        request.message, full_response,
        recent_history, profile, db
    ))


async def _post_reply_tasks(
    user_id: str,
    platform: str,
    session_id: str,
    user_message: str,
    assistant_reply: str,
    recent_history: list[dict],
    profile,
    db: AsyncSession,
) -> None:
    """
    All post-reply work runs here as a background task.
    None of this blocks the streamed response.
    """
    try:
        # Persist messages
        await conversation_history_service.store_message(
            user_id, platform, session_id, "user", user_message, db
        )
        await conversation_history_service.store_message(
            user_id, platform, session_id, "assistant", assistant_reply, db
        )

        # Update structured memory profile
        updates = await memory_service.extract_profile_updates(
            user_message, assistant_reply, profile
        )
        await memory_service.update_profile(user_id, platform, updates, db)

        # Background: extract session memories from this exchange
        from services.session_memory_service import extract_and_store
        await extract_and_store(
            user_id, platform, session_id,
            recent_history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_reply},
            ],
            db,
        )

        # Background: AutoDream consolidation (checks its own gate)
        from services.auto_dream_service import maybe_dream
        await maybe_dream(user_id, platform, db)

        # Log feedback
        await feedback_service.store_feedback_log(
            user_id=user_id,
            platform=platform,
            session_id=session_id,
            service="chat",
            request_data={"message": user_message},
            response_data={"response": assistant_reply[:500]},
            provider_used="groq",
            model_used="",
            response_ms=0,
            db=db,
        )

        # Old-style history summarization (now supplemented by compact_service)
        await conversation_history_service.summarize_old_history(user_id, platform, db)

    except Exception:
        pass
