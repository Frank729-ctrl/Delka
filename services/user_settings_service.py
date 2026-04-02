"""
User settings sync — exceeds Claude Code's settingsSync service.

src: Syncs local settings files to cloud across Claude Code sessions.
Delka: Per-user preferences stored in DB, applied automatically to every
       request. Users can set preferences via chat ("always respond in French",
       "keep answers short", "use bullet points").

Settings are extracted from corrections and explicit instructions,
stored in the settings_store table, and merged into the system prompt.

Setting categories:
- language:      preferred response language
- length:        preferred response length (brief/normal/detailed)
- format:        preferred format (bullets/narrative/code_only)
- tone:          formal/casual
- platform_role: user's role on the platform (e.g. "job seeker", "developer")
- custom:        any user-defined preferences
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json

_PREFERENCE_PATTERNS = {
    # "always respond in French" → language=fr
    r"always respond in (\w+)": ("language", lambda m: m.group(1).lower()),
    r"respond in (\w+) (please|always|from now on)": ("language", lambda m: m.group(1).lower()),
    # "keep it short" → length=brief
    r"(keep|make) (it |your answers |responses )?(short|brief|concise)": ("length", lambda m: "brief"),
    r"give me (more )?detail": ("length", lambda m: "detailed"),
    # "use bullet points" → format=bullets
    r"use bullet points": ("format", lambda m: "bullets"),
    r"don.t use bullet points": ("format", lambda m: "narrative"),
    # "be more formal" → tone=formal
    r"be (more )?formal": ("tone", lambda m: "formal"),
    r"be (more )?casual": ("tone", lambda m: "casual"),
}


async def extract_and_save_preferences(
    message: str,
    user_id: str,
    platform: str,
    db: AsyncSession,
) -> dict:
    """
    Scan a user message for preference-setting instructions.
    Returns dict of any settings extracted and saved.
    """
    import re
    extracted = {}

    for pattern, (key, extractor) in _PREFERENCE_PATTERNS.items():
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            try:
                value = extractor(match)
                extracted[key] = value
            except Exception:
                pass

    if extracted:
        await _save_settings(user_id, platform, extracted, db)

    return extracted


async def _save_settings(
    user_id: str,
    platform: str,
    settings: dict,
    db: AsyncSession,
) -> None:
    for key, value in settings.items():
        try:
            await db.execute(
                text(
                    "INSERT INTO user_settings (user_id, platform, setting_key, setting_value, updated_at) "
                    "VALUES (:uid, :pl, :k, :v, NOW()) "
                    "ON DUPLICATE KEY UPDATE setting_value = :v, updated_at = NOW()"
                ),
                {"uid": user_id, "pl": platform, "k": key, "v": str(value)},
            )
        except Exception:
            pass
    try:
        await db.commit()
    except Exception:
        pass


async def get_user_settings(
    user_id: str,
    platform: str,
    db: AsyncSession,
) -> dict:
    """Load all settings for a user."""
    try:
        result = await db.execute(
            text(
                "SELECT setting_key, setting_value FROM user_settings "
                "WHERE user_id = :uid AND platform = :pl"
            ),
            {"uid": user_id, "pl": platform},
        )
        return {row[0]: row[1] for row in result.fetchall()}
    except Exception:
        return {}


def build_settings_instruction(settings: dict) -> str:
    """Convert user settings into system prompt instructions."""
    parts = []

    lang = settings.get("language", "")
    if lang and lang not in ("en", "english"):
        parts.append(f"LANGUAGE: Always respond in {lang}.")

    length = settings.get("length", "")
    if length == "brief":
        parts.append("LENGTH: Keep responses short and direct.")
    elif length == "detailed":
        parts.append("LENGTH: Give detailed, thorough responses.")

    fmt = settings.get("format", "")
    if fmt == "bullets":
        parts.append("FORMAT: Use bullet points by default.")
    elif fmt == "narrative":
        parts.append("FORMAT: Use flowing prose, not bullet points.")

    tone = settings.get("tone", "")
    if tone:
        parts.append(f"TONE: Be {tone}.")

    return "\n".join(parts)
