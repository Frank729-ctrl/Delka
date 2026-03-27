import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_or_create_profile(user_id: str, platform: str, db: AsyncSession):
    from models.user_memory_profile_model import UserMemoryProfile

    result = await db.execute(
        select(UserMemoryProfile).where(
            UserMemoryProfile.user_id == user_id,
            UserMemoryProfile.platform == platform,
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = UserMemoryProfile(
            user_id=user_id,
            platform=platform,
            correction_rules=[],
            preferences={},
            cv_profile={},
            topics_discussed=[],
        )
        db.add(profile)
        await db.flush()
    return profile


async def update_profile(
    user_id: str,
    platform: str,
    updates: dict,
    db: AsyncSession,
) -> None:
    profile = await get_or_create_profile(user_id, platform, db)
    now = datetime.utcnow()
    for key, value in updates.items():
        if hasattr(profile, key):
            setattr(profile, key, value)
    profile.last_seen = now
    profile.total_interactions = (profile.total_interactions or 0) + 1
    profile.updated_at = now


async def add_correction_rule(
    user_id: str,
    platform: str,
    rule: str,
    db: AsyncSession,
) -> None:
    profile = await get_or_create_profile(user_id, platform, db)
    rules = list(profile.correction_rules or [])

    # Deduplicate
    if rule in rules:
        return

    rules.append(rule)

    # Max 20 rules — remove oldest
    if len(rules) > 20:
        rules = rules[-20:]

    profile.correction_rules = rules
    profile.updated_at = datetime.utcnow()


_NAME_PATTERNS = [
    re.compile(r"(?:i'?m|i am|my name is|call me)\s+([A-Z][a-z]{1,30})", re.IGNORECASE),
]

_TITLE_PATTERNS = [
    re.compile(
        r"(?:i work as a?|i am a?|i'm a?)\s+([a-z][a-z\s]{2,40}?)(?:\.|,|$|\s+at\s)",
        re.IGNORECASE,
    ),
]

_SKILL_PATTERNS = [
    re.compile(
        r"(?:i (?:know|use|work with|code in|program in))\s+([A-Za-z][A-Za-z+#\s]{1,30}?)(?:\.|,|and|$)",
        re.IGNORECASE,
    ),
]

_FORMALITY_CONTRACTIONS = re.compile(
    r"\b(i'm|don't|can't|won't|it's|we're|they're|i've|you've|haven't|isn't)\b",
    re.IGNORECASE,
)


async def extract_profile_updates(
    user_message: str,
    assistant_response: str,
    existing_profile,
) -> dict:
    updates = {}

    # Name extraction
    if not getattr(existing_profile, "name", None):
        for pattern in _NAME_PATTERNS:
            m = pattern.search(user_message)
            if m:
                updates["name"] = m.group(1).strip().title()
                break

    # Job title extraction
    existing_cv = dict(getattr(existing_profile, "cv_profile", None) or {})
    if not existing_cv.get("job_title"):
        for pattern in _TITLE_PATTERNS:
            m = pattern.search(user_message)
            if m:
                title = m.group(1).strip().title()
                if len(title) > 2:
                    existing_cv["job_title"] = title
                    updates["cv_profile"] = existing_cv
                    break

    # Tone inference from message
    contraction_count = len(_FORMALITY_CONTRACTIONS.findall(user_message))
    word_count = len(user_message.split())
    if word_count > 0:
        if contraction_count >= 2 or word_count < 10:
            if getattr(existing_profile, "tone_preference", "adaptive") == "adaptive":
                updates["tone_preference"] = "casual"
        elif word_count > 30 and contraction_count == 0:
            if getattr(existing_profile, "tone_preference", "adaptive") == "adaptive":
                updates["tone_preference"] = "formal"

    return updates


async def build_memory_context_string(
    profile,
    recent_history: list[dict],
    rag_examples: list[dict],
) -> str:
    from prompts.memory_prompt import build_memory_context
    return build_memory_context(profile, recent_history, rag_examples)
