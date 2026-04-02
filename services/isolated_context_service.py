"""
Isolated Context (Worktree) — exceeds Claude Code's EnterWorktree/ExitWorktree.

src: Git worktrees give each task an isolated copy of the repo to work in.
Delka: Isolated memory contexts for coordinator subtasks. When running parallel
       or sequential subtasks, each gets its own context bubble:
       - own system prompt slice
       - own message history (starts fresh)
       - own tool results
       - merged back into the parent context on completion

This prevents subtask A's tool results from polluting subtask B's reasoning,
which was causing incorrect answers in multi-part coordinator responses.

Use cases:
- Coordinator running "research Ghana job market" + "tailor CV" in parallel
- Plan mode executing steps 1→2→3 without step 1's noise bleeding into step 3
- Multi-document processing (each doc gets its own read context)

API:
  ctx = create_context(parent_session_id, task_name)
  add_message(ctx_id, role, content)
  get_messages(ctx_id)
  merge_result(ctx_id, parent_session_id) → merged summary
  destroy_context(ctx_id)
"""
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IsolatedContext:
    ctx_id: str
    parent_session_id: str
    task_name: str
    system_prompt: str = ""
    messages: list[dict] = field(default_factory=list)
    result: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    is_active: bool = True


# ── In-memory store ────────────────────────────────────────────────────────────
_contexts: dict[str, IsolatedContext] = {}
_CONTEXT_TTL = 1800   # 30 minutes — auto-evict stale contexts


def _evict_stale() -> None:
    now = time.time()
    stale = [cid for cid, ctx in _contexts.items() if now - ctx.created_at > _CONTEXT_TTL]
    for cid in stale:
        del _contexts[cid]


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def create_context(
    parent_session_id: str,
    task_name: str,
    system_prompt: str = "",
    seed_messages: Optional[list[dict]] = None,
) -> IsolatedContext:
    """
    Create an isolated context for a subtask.
    Optionally seed it with selected messages from parent (not the full history).
    """
    _evict_stale()
    ctx = IsolatedContext(
        ctx_id=f"ctx-{str(uuid.uuid4())[:8]}",
        parent_session_id=parent_session_id,
        task_name=task_name,
        system_prompt=system_prompt,
        messages=list(seed_messages or []),
    )
    _contexts[ctx.ctx_id] = ctx
    return ctx


def add_message(ctx_id: str, role: str, content: str) -> None:
    ctx = _contexts.get(ctx_id)
    if ctx:
        ctx.messages.append({"role": role, "content": content})


def get_messages(ctx_id: str) -> list[dict]:
    ctx = _contexts.get(ctx_id)
    return ctx.messages if ctx else []


def get_context(ctx_id: str) -> Optional[IsolatedContext]:
    return _contexts.get(ctx_id)


def set_result(ctx_id: str, result: str) -> None:
    ctx = _contexts.get(ctx_id)
    if ctx:
        ctx.result = result
        ctx.completed_at = time.time()
        ctx.is_active = False


def destroy_context(ctx_id: str) -> None:
    _contexts.pop(ctx_id, None)


def list_contexts(parent_session_id: str) -> list[IsolatedContext]:
    return [ctx for ctx in _contexts.values() if ctx.parent_session_id == parent_session_id]


# ── Parallel execution ────────────────────────────────────────────────────────

async def run_in_isolated_context(
    parent_session_id: str,
    task_name: str,
    task_prompt: str,
    system_prompt: str = "",
    seed_messages: Optional[list[dict]] = None,
) -> tuple[str, str]:
    """
    Run a single subtask in an isolated context.
    Returns (ctx_id, result_text).
    """
    ctx = create_context(parent_session_id, task_name, system_prompt, seed_messages)

    try:
        from services.inference_service import generate_full_response
        messages_for_inference = []
        if ctx.messages:
            messages_for_inference = ctx.messages.copy()
        messages_for_inference.append({"role": "user", "content": task_prompt})

        # Store user message in isolated context
        add_message(ctx.ctx_id, "user", task_prompt)

        text, provider, model = await generate_full_response(
            task="support",
            system_prompt=system_prompt,
            user_prompt=task_prompt,
            temperature=0.5,
            max_tokens=1024,
        )

        add_message(ctx.ctx_id, "assistant", text)
        set_result(ctx.ctx_id, text)
        return ctx.ctx_id, text

    except Exception as e:
        error_msg = f"[Subtask '{task_name}' failed: {e}]"
        set_result(ctx.ctx_id, error_msg)
        return ctx.ctx_id, error_msg


async def run_parallel_subtasks(
    parent_session_id: str,
    subtasks: list[dict],   # [{"name": str, "prompt": str, "system": str}, ...]
) -> list[dict]:
    """
    Run multiple subtasks in parallel, each in isolation.
    Returns list of {name, result} dicts.
    """
    import asyncio
    tasks = [
        run_in_isolated_context(
            parent_session_id=parent_session_id,
            task_name=st["name"],
            task_prompt=st["prompt"],
            system_prompt=st.get("system", ""),
            seed_messages=st.get("seed_messages"),
        )
        for st in subtasks
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    output = []
    for i, res in enumerate(results):
        name = subtasks[i]["name"]
        if isinstance(res, Exception):
            output.append({"name": name, "result": f"[Error: {res}]"})
        else:
            ctx_id, text = res
            output.append({"name": name, "result": text, "ctx_id": ctx_id})
    return output


def merge_results(results: list[dict], separator: str = "\n\n---\n\n") -> str:
    """Merge subtask results into a single response for the parent context."""
    parts = []
    for r in results:
        parts.append(f"**{r['name']}**\n{r['result']}")
    return separator.join(parts)
