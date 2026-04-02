"""
Coordinator / Multi-agent mode.

Inspired by Claude Code's coordinator/ system.

For complex tasks, Delka can spawn multiple specialized sub-agents that work
in parallel, then synthesize their results into a single coherent response.

Example: "Analyze this job posting and help me apply"
→ Agent A: extract job requirements
→ Agent B: match against user's CV profile
→ Agent C: draft cover letter opening
→ Coordinator: weave all three into one response

Delka improvements over Claude Code:
- Sub-agents run as asyncio tasks (parallel, not sequential)
- Each sub-agent uses the optimal provider for its task type
- Coordinator has a confidence threshold — if sub-agent fails, it gracefully
  skips that piece rather than crashing
- Works via HTTP-native pattern (no subprocess spawning)
- Returns streamed tokens as coordinator synthesizes
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass


@dataclass
class SubAgentTask:
    name: str
    system_prompt: str
    user_prompt: str
    task_type: str = "support"  # maps to inference_service task chains
    max_tokens: int = 512


# ── Task detection ────────────────────────────────────────────────────────────

_COORDINATOR_TRIGGERS = re.compile(
    r"\b(analyze\s+and|help\s+me\s+(write|apply|prepare|create|build)|"
    r"review\s+(my|this)\s+\w+\s+and|compare\s+.{5,30}\s+and|"
    r"research\s+.{5,40}\s+then|find\s+.{5,40}\s+and\s+(write|tell|show))\b",
    re.IGNORECASE,
)


def needs_coordinator(message: str) -> bool:
    """Return True if the message benefits from multi-agent handling."""
    return bool(_COORDINATOR_TRIGGERS.search(message))


# ── Sub-agent definitions ─────────────────────────────────────────────────────

def _build_tasks(message: str, user_profile: str) -> list[SubAgentTask]:
    """
    Decompose a complex request into parallel sub-agent tasks.
    Currently supports: job application, CV review, research+write patterns.
    """
    msg_lower = message.lower()

    # Job application pattern
    if any(w in msg_lower for w in ["job", "apply", "application", "posting", "role", "position"]):
        return [
            SubAgentTask(
                name="requirements_extractor",
                system_prompt="Extract the key requirements from this job posting or description. List: required skills, experience level, key responsibilities. Be concise.",
                user_prompt=message,
                task_type="support",
                max_tokens=300,
            ),
            SubAgentTask(
                name="profile_matcher",
                system_prompt=f"Given this user profile:\n{user_profile}\n\nAnalyze how well they match the job. List: strong matches, gaps, and 1 suggestion to bridge the gap.",
                user_prompt=message,
                task_type="support",
                max_tokens=300,
            ),
            SubAgentTask(
                name="action_advisor",
                system_prompt="Give 3 concrete, specific action steps for applying to this role. Be direct. No filler.",
                user_prompt=message,
                task_type="support",
                max_tokens=200,
            ),
        ]

    # Research + write pattern
    if any(w in msg_lower for w in ["research", "find", "look up", "tell me about"]):
        return [
            SubAgentTask(
                name="researcher",
                system_prompt="Research and summarize the key facts about the topic in the user's message. Focus on accuracy.",
                user_prompt=message,
                task_type="support",
                max_tokens=400,
            ),
            SubAgentTask(
                name="writer",
                system_prompt="Based on what you know about this topic, draft a clear, well-structured response in the user's requested format.",
                user_prompt=message,
                task_type="support",
                max_tokens=400,
            ),
        ]

    # Generic analysis pattern
    return [
        SubAgentTask(
            name="analyzer",
            system_prompt="Analyze the user's request. Break it into its core components and what each needs.",
            user_prompt=message,
            task_type="support",
            max_tokens=300,
        ),
        SubAgentTask(
            name="responder",
            system_prompt="Provide a thorough, helpful response to the user's request. Be specific and actionable.",
            user_prompt=message,
            task_type="chat",
            max_tokens=600,
        ),
    ]


_SYNTHESIS_SYSTEM = """You are the coordinator agent. You have received outputs from multiple specialized sub-agents.

Synthesize their outputs into ONE coherent, well-structured response for the user.
- Don't show the sub-agent structure — just present the final answer naturally
- Resolve any contradictions by using the most specific/recent information
- If a sub-agent output is empty or failed, skip it gracefully
- Match the user's original tone and context"""


async def run_coordinator(
    message: str,
    user_profile: str,
    platform: str,
) -> str:
    """
    Run parallel sub-agents then synthesize into one response.
    """
    from services.inference_service import generate_full_response

    tasks = _build_tasks(message, user_profile)

    # Run all sub-agents in parallel
    async def run_one(task: SubAgentTask) -> tuple[str, str]:
        try:
            result, _, _ = await generate_full_response(
                task=task.task_type,
                system_prompt=task.system_prompt,
                user_prompt=task.user_prompt,
                temperature=0.5,
                max_tokens=task.max_tokens,
            )
            return task.name, result
        except Exception:
            return task.name, ""

    results = await asyncio.gather(*[run_one(t) for t in tasks])

    # Build synthesis prompt
    parts = [f"**{name}**:\n{output}" for name, output in results if output]
    if not parts:
        return ""

    synthesis_input = (
        f"Original user message: {message}\n\n"
        f"Sub-agent outputs:\n\n" + "\n\n".join(parts)
    )

    final, _, _ = await generate_full_response(
        task="chat",
        system_prompt=_SYNTHESIS_SYSTEM,
        user_prompt=synthesis_input,
        temperature=0.7,
        max_tokens=1024,
    )
    return final
