"""
Plan mode — exceeds Claude Code's EnterPlanMode/ExitPlanMode tools.

src: User manually enters plan mode; agent stops to outline before acting.
Delka: AUTO-detects when planning is needed (complex multi-step tasks),
       generates a structured plan + estimated steps, streams it to user,
       then executes each step. User can approve or skip.

Trigger patterns: multi-part requests, "build me a...", "create a full...",
"step by step", "complete workflow", etc.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

_PLAN_TRIGGERS = re.compile(
    r"\b(build|create|set up|implement|design|write a full|complete|"
    r"step[\s-]by[\s-]step|end[\s-]to[\s-]end|from scratch|"
    r"entire|whole system|full workflow|everything|pipeline)\b",
    re.IGNORECASE,
)

_MULTI_PART = re.compile(
    r"\b(and (also|then)|plus|additionally|as well as|on top of that|"
    r"furthermore|step \d|part \d|\d\.\s+\w|\d\)\s+\w)\b",
    re.IGNORECASE,
)

_MIN_WORDS_FOR_PLAN = 15  # Short messages don't need planning


@dataclass
class Plan:
    title: str
    steps: list[str]
    estimated_minutes: int
    requires_approval: bool = False


_PLAN_SYSTEM = """You are a task planner. Given a user's request, output a concise plan.

Format EXACTLY as:
TITLE: [3-7 word task title]
STEPS:
1. [step]
2. [step]
...
ESTIMATE: [N] minutes

Rules:
- 3 to 6 steps maximum
- Each step max 12 words
- Be specific to the actual request
- Estimate total time realistically
"""


def needs_plan_mode(message: str) -> bool:
    """Returns True if the message warrants structured planning."""
    words = len(message.split())
    if words < _MIN_WORDS_FOR_PLAN:
        return False
    has_trigger = bool(_PLAN_TRIGGERS.search(message))
    has_multi_part = bool(_MULTI_PART.search(message))
    return has_trigger or (has_multi_part and words > 25)


async def generate_plan(message: str, platform: str = "") -> Optional[Plan]:
    """
    Generate a structured plan for a complex request.
    Returns None if planning fails (caller falls through to normal chat).
    """
    try:
        from services.inference_service import generate_full_response
        raw, _, _ = await generate_full_response(
            task="support",
            system_prompt=_PLAN_SYSTEM,
            user_prompt=message[:1000],
            temperature=0.3,
            max_tokens=300,
        )
        return _parse_plan(raw)
    except Exception:
        return None


def _parse_plan(raw: str) -> Optional[Plan]:
    """Parse the structured plan output."""
    try:
        lines = raw.strip().split("\n")
        title = ""
        steps = []
        estimate = 5

        for line in lines:
            line = line.strip()
            if line.startswith("TITLE:"):
                title = line[6:].strip()
            elif line.startswith("ESTIMATE:"):
                try:
                    estimate = int(re.search(r"\d+", line).group())
                except Exception:
                    pass
            elif re.match(r"^\d+\.", line):
                step = re.sub(r"^\d+\.\s*", "", line).strip()
                if step:
                    steps.append(step)

        if not title or not steps:
            return None

        return Plan(title=title, steps=steps, estimated_minutes=estimate)
    except Exception:
        return None


def format_plan_for_stream(plan: Plan) -> str:
    """Format plan as markdown for streaming to the user."""
    lines = [
        f"**Plan: {plan.title}**",
        f"_~{plan.estimated_minutes} minutes · {len(plan.steps)} steps_",
        "",
    ]
    for i, step in enumerate(plan.steps, 1):
        lines.append(f"{i}. {step}")
    lines += ["", "---", ""]
    return "\n".join(lines)
