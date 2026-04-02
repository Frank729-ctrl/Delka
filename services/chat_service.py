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
from services.relevant_memory_service import get_relevant_memories, format_memories_for_prompt
from services.team_memory_service import get_team_context
from services.context_analytics_service import analyze_context
from services.tool_attribution_service import (
    ToolUsage, build_attribution_footnote, detect_plugins_from_context
)
from services.tips_service import get_tip_for_user, get_shown_tips, mark_tip_shown, inject_tip_into_prompt
from services.adaptive_length_service import build_length_instruction
from services.user_settings_service import (
    extract_and_save_preferences, get_user_settings, build_settings_instruction
)
from services.plan_mode_service import needs_plan_mode, generate_plan, format_plan_for_stream
from services.policy_limits_service import check_and_increment, load_platform_limits
from services.speculation_service import speculate_background
from services.analytics_service import log_event, get_feature_flag
from services.webfetch_service import needs_fetch, extract_url, fetch_url, build_fetch_context
from services.workspace_service import needs_workspace, list_files, search_workspace, build_workspace_context
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

    # ── 1b. Policy limits — check quotas before doing any work ───────────────
    platform_limits = await load_platform_limits(platform, db)
    allowed, limit_reason = check_and_increment(platform, user_id, limits=platform_limits)
    if not allowed:
        yield f"data: {json.dumps({'type': 'error', 'content': limit_reason})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # ── 2. Away summary — if user was gone > 30 min, show recap first ─────────
    from services.away_summary_service import get_away_summary
    away_recap = await get_away_summary(user_id, platform, session_id, db)
    if away_recap and not recent_history:
        # Only show recap at session start (no messages yet this turn)
        yield f"data: {json.dumps({'type': 'away_summary', 'content': away_recap})}\n\n"

    # ── 3. Language + tone + user settings (parallel) ────────────────────────
    lang = detect_language(request.message)
    language_instruction = get_language_instruction(lang)
    tone_analysis = analyze_user_tone(request.message)

    # Extract any preference-setting instructions from this message, load current settings
    await extract_and_save_preferences(request.message, user_id, platform, db)
    user_settings = await get_user_settings(user_id, platform, db)

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

    # ── 7b. Plan mode — structured plan before complex multi-step tasks ──────
    if get_feature_flag("plan_mode", True) and needs_plan_mode(request.message):
        plan = await generate_plan(request.message, platform)
        if plan:
            plan_text = format_plan_for_stream(plan)
            yield f"data: {json.dumps({'type': 'plan', 'content': plan_text})}\n\n"
            log_event("plan_mode_triggered", platform=platform, user_id=user_id)

    # ── 8. Plugins + web search + relevant memories (parallel) ───────────────
    context_hint = ""
    for entry in reversed(recent_history):
        if entry["role"] == "user" and len(entry["content"].split()) >= 3:
            context_hint = entry["content"]
            break

    search_task = None
    search_query_used = ""
    if needs_search(request.message):
        search_query_used = extract_search_query(request.message, context_hint=context_hint)
        search_task = asyncio.create_task(search(search_query_used))

    # WebFetch: if message contains a URL to read, fetch it in parallel
    fetch_task = None
    if needs_fetch(request.message):
        url = extract_url(request.message)
        if url:
            fetch_task = asyncio.create_task(fetch_url(url))

    # Workspace: if message references user's files, load context
    workspace_task = None
    if needs_workspace(request.message):
        workspace_task = asyncio.create_task(
            search_workspace(user_id, platform, request.message[:100], db)
        )

    plugin_context, search_context, relevant_mems, team_ctx, fetch_result, workspace_results = await asyncio.gather(
        run_plugins(request.message),
        search_task if search_task else _noop(),
        get_relevant_memories(request.message, user_id, platform, db),
        get_team_context(platform, db),
        fetch_task if fetch_task else _noop(),
        workspace_task if workspace_task else _noop(),
    )

    # ── 9. Build system prompt ────────────────────────────────────────────────
    system_prompt = build_chat_system_prompt(
        platform=platform,
        profile=profile,
        recent_history=recent_history,
        rag_examples=rag_examples,
        tone_analysis=tone_analysis,
        language_instruction=language_instruction,
    )

    # Inject: team context → relevant memories → plugin context → search
    if team_ctx:
        system_prompt = f"{system_prompt}\n\n{team_ctx}"
    mem_section = format_memories_for_prompt(relevant_mems)
    if mem_section:
        system_prompt = f"{system_prompt}\n\n{mem_section}"
    if plugin_context:
        system_prompt = f"{system_prompt}\n\n{plugin_context}"
    if search_context:
        system_prompt = f"{system_prompt}\n\n{search_context}"

    # WebFetch result
    if fetch_result and isinstance(fetch_result, dict):
        fetch_ctx = build_fetch_context(fetch_result)
        if fetch_ctx:
            system_prompt = f"{system_prompt}\n\n{fetch_ctx}"
            log_event("webfetch_used", platform=platform, user_id=user_id,
                      url=fetch_result.get("url", ""))

    # Workspace search results
    if workspace_results and isinstance(workspace_results, list):
        workspace_files = await list_files(user_id, platform, db)
        ws_ctx = build_workspace_context(workspace_files, workspace_results)
        if ws_ctx:
            system_prompt = f"{system_prompt}\n\n{ws_ctx}"

    # ── 9b. Adaptive length + user settings + tips ───────────────────────────
    # Adaptive length: auto-detect intent (brief/detailed/bullets/code-only)
    if get_feature_flag("brief_mode", True):
        length_instr = build_length_instruction(request.message)
        if length_instr:
            system_prompt = f"{length_instr}\n\n{system_prompt}"

    # User settings: persistent preferences ("always in French", "use bullets")
    settings_instr = build_settings_instruction(user_settings)
    if settings_instr:
        system_prompt = f"{settings_instr}\n\n{system_prompt}"

    # Tips: inject once per user per tip, non-intrusively
    profile_dict = profile.__dict__ if hasattr(profile, "__dict__") else {}
    shown_tips = get_shown_tips(user_id, profile_dict)
    msg_count = len(recent_history) // 2
    tip_result = get_tip_for_user(user_id, msg_count, request.message, shown_tips)
    if tip_result:
        tip_id, tip_text = tip_result
        system_prompt = inject_tip_into_prompt(system_prompt, tip_text)
        mark_tip_shown(user_id, tip_id)

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

    # ── 11b. Context analytics — warn before limit ────────────────────────────
    ctx_breakdown = analyze_context(
        system_prompt=system_prompt,
        history=[m for m in messages if m["role"] != "system"],
        current_message=request.message,
        plugin_context=plugin_context,
        search_context=search_context,
        model=current_model,
    )
    if ctx_breakdown.is_critical:
        yield f"data: {json.dumps({'type': 'context_warning', 'pct': ctx_breakdown.utilization_pct, 'msg': ctx_breakdown.warnings[0] if ctx_breakdown.warnings else ''})}\n\n"

    # ── 12. Stream from inference with live LSP feedback ─────────────────────
    from services.lsp_feedback_service import LSPStreamState, process_token, finalize as lsp_finalize
    lsp_state = LSPStreamState()
    tokens: list[str] = []

    async for token in _inference_stream("chat", messages):
        tokens.append(token)
        yield f"data: {token}\n\n"
        # Emit any LSP diagnostic events triggered by this token
        for lsp_event in process_token(lsp_state, token):
            yield lsp_event

    full_response = "".join(tokens)

    # Final full LSP pass after streaming completes
    for lsp_event in lsp_finalize(lsp_state, full_response):
        yield lsp_event

    # ── 12b. Tool attribution footnote ────────────────────────────────────────
    usage_obj = ToolUsage(
        search_fired=bool(search_query_used),
        search_query=search_query_used,
        plugins_fired=detect_plugins_from_context(plugin_context),
    )
    attribution = build_attribution_footnote(usage_obj)
    if attribution:
        yield f"data: {attribution}\n\n"
        full_response += attribution

    # Send context usage stats (frontend can show a subtle bar)
    if ctx_breakdown.utilization_pct > 60:
        yield f"data: {json.dumps({'type': 'context_usage', 'pct': ctx_breakdown.utilization_pct})}\n\n"

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

        # Pre-generate follow-up questions for next turn (speculation)
        if get_feature_flag("speculation", True):
            asyncio.create_task(speculate_background(
                session_id=session_id,
                assistant_reply=assistant_reply,
                platform=platform,
            ))

        # Log request completion event
        log_event("request_completed", platform=platform, user_id=user_id, service="chat")

    except Exception:
        pass
