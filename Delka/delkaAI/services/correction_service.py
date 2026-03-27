import re
from sqlalchemy.ext.asyncio import AsyncSession

CORRECTION_PATTERNS = [
    "don't say",
    "stop saying",
    "don't call me",
    "don't use the word",
    "i prefer",
    "instead say",
    "that's wrong",
    "actually",
    "not like that",
    "can you be more",
    "too formal",
    "too casual",
    "shorter please",
    "more detail",
    "explain better",
    "wrong tone",
    "sounds robotic",
    "sounds too stiff",
    "please keep",
    "stop using",
    "be more concise",
    "be more brief",
    "keep it short",
]

_CORRECTION_RE = re.compile(
    "|".join(re.escape(p) for p in CORRECTION_PATTERNS),
    re.IGNORECASE,
)


def is_correction(message: str) -> bool:
    return bool(_CORRECTION_RE.search(message))


async def extract_and_store_correction(
    message: str,
    user_id: str,
    platform: str,
    db: AsyncSession,
) -> str | None:
    if not is_correction(message):
        return None

    from services.memory_service import add_correction_rule
    from services.inference_service import generate_full_response

    try:
        rule_text, _, _ = await generate_full_response(
            task="support",
            system_prompt=(
                "Extract the user's preference rule from their message. "
                "Return ONE clear rule starting with a verb (Never, Always, Keep, Avoid, Use). "
                "Example: 'Never address user as dear'. "
                "Return ONLY the rule. Nothing else. No explanation."
            ),
            user_prompt=message,
            temperature=0.1,
            max_tokens=50,
        )
        rule = rule_text.strip().strip('"').strip("'")
    except Exception:
        # Fallback: use the message itself trimmed
        rule = message[:200].strip()

    if rule:
        await add_correction_rule(user_id, platform, rule, db)

    return "Got it — I'll remember that."
