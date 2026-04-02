"""
Tips / onboarding system — inspired by Claude Code's tips/ service.

Shows contextual hints to users based on:
- How many messages they've sent (session count)
- What they've been using (detected patterns)
- What they haven't discovered yet

Tips are injected as a subtle note in the chat system prompt,
shown only once per tip per user (tracked in DB).
Never shown more than once per session.
"""
import random
from dataclasses import dataclass

# ── Tip definitions ────────────────────────────────────────────────────────────

@dataclass
class Tip:
    id: str
    trigger_after_messages: int     # Show after this many total messages
    text: str
    relevant_if: str = ""           # Optional: only show if message contains this keyword


TIPS: list[Tip] = [
    Tip(
        id="calculator",
        trigger_after_messages=3,
        text="Tip: Ask me to calculate anything — 'What is 15% of GHS 450?' — I use a safe calculator, not guesswork.",
    ),
    Tip(
        id="weather",
        trigger_after_messages=5,
        text="Tip: I can check live weather — try 'What's the weather in Kumasi right now?'",
    ),
    Tip(
        id="currency",
        trigger_after_messages=8,
        text="Tip: I have live exchange rates — ask 'How much is $200 in cedis today?'",
    ),
    Tip(
        id="bible",
        trigger_after_messages=10,
        text="Tip: I can look up Bible verses — try 'What does John 3:16 say?' or 'Give me Proverbs 3:5-6'",
    ),
    Tip(
        id="cv_raw",
        trigger_after_messages=15,
        text="Tip: You can generate a CV just by describing yourself — no forms needed. Try the CV endpoint with raw_text.",
        relevant_if="cv",
    ),
    Tip(
        id="translate",
        trigger_after_messages=12,
        text="Tip: I can translate text — try 'Translate this to Twi: Welcome to Ghana'",
    ),
    Tip(
        id="code",
        trigger_after_messages=20,
        text="Tip: Ask me to write code — 'Write a Python function to validate a Ghana phone number' — I use Cerebras Qwen3 for code.",
        relevant_if="code",
    ),
    Tip(
        id="search",
        trigger_after_messages=7,
        text="Tip: I search the web automatically for current events, news, and people. Just ask naturally.",
    ),
    Tip(
        id="news",
        trigger_after_messages=25,
        text="Tip: Ask 'What's the latest news in Ghana?' — I pull live headlines from GNews.",
    ),
    Tip(
        id="memory",
        trigger_after_messages=30,
        text="Tip: I remember things you tell me across conversations — your name, preferences, job. The more we talk, the better I know you.",
    ),
    Tip(
        id="skills",
        trigger_after_messages=18,
        text="Tip: Try slash commands — /summarize, /translate, /explain, /improve, /debug, /brainstorm — for structured tasks.",
    ),
    Tip(
        id="image",
        trigger_after_messages=35,
        text="Tip: I can generate images — try 'Create an image of a Ghanaian market scene at sunset'",
    ),
]

_TIPS_BY_ID = {t.id: t for t in TIPS}

# ── State tracking (in-memory per process, backed by user profile) ─────────────

_shown_tips_cache: dict[str, set[str]] = {}  # user_id → set of tip IDs shown


def get_tip_for_user(
    user_id: str,
    message_count: int,
    current_message: str,
    shown_tip_ids: set[str],
) -> str | None:
    """
    Returns the text of a tip to show this turn, or None.
    Prioritises tips the user hasn't seen and whose trigger threshold is met.
    """
    eligible = []
    msg_lower = current_message.lower()

    for tip in TIPS:
        if tip.id in shown_tip_ids:
            continue
        if message_count < tip.trigger_after_messages:
            continue
        if tip.relevant_if and tip.relevant_if not in msg_lower:
            continue
        eligible.append(tip)

    if not eligible:
        return None

    # Pick the one with the lowest trigger threshold (most overdue)
    chosen = min(eligible, key=lambda t: t.trigger_after_messages)
    return chosen.id, chosen.text


def mark_tip_shown(user_id: str, tip_id: str) -> None:
    """Record that this tip was shown to this user."""
    _shown_tips_cache.setdefault(user_id, set()).add(tip_id)


def get_shown_tips(user_id: str, profile: dict) -> set[str]:
    """Load shown tips from memory cache or user profile."""
    cached = _shown_tips_cache.get(user_id)
    if cached is not None:
        return cached
    # Read from profile if available
    shown_raw = profile.get("shown_tips", "") if isinstance(profile, dict) else ""
    shown = set(shown_raw.split(",")) if shown_raw else set()
    _shown_tips_cache[user_id] = shown
    return shown


def inject_tip_into_prompt(system_prompt: str, tip_text: str) -> str:
    """Append tip as a gentle footnote to the system prompt."""
    return f"{system_prompt}\n\n---\n{tip_text}"
