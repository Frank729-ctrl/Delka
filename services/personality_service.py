import re
from prompts.personality_prompt import PLATFORM_PERSONALITIES

_CONTRACTION_RE = re.compile(
    r"\b(i'm|don't|can't|won't|it's|we're|they're|i've|you've|haven't|isn't|that's|there's|here's)\b",
    re.IGNORECASE,
)
_EMOJI_RE = re.compile(
    r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    r"\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251]+",
    flags=re.UNICODE,
)
_FRUSTRATION_RE = re.compile(
    r"\b(frustrated|annoyed|terrible|useless|awful|broken|doesn'?t work|not working|what the|wtf)\b",
    re.IGNORECASE,
)
_URGENCY_RE = re.compile(
    r"\b(urgent|asap|immediately|right now|need this now|hurry|quickly|fast|emergency)\b",
    re.IGNORECASE,
)


def analyze_user_tone(message: str) -> dict:
    words = message.split()
    word_count = len(words)
    contraction_count = len(_CONTRACTION_RE.findall(message))
    has_emoji = bool(_EMOJI_RE.search(message))
    has_lowercase_only = message == message.lower() and word_count > 3
    sentence_count = max(1, message.count(".") + message.count("!") + message.count("?"))
    avg_sentence_len = word_count / sentence_count

    # Formality detection
    casual_signals = contraction_count + (2 if has_emoji else 0) + (1 if has_lowercase_only else 0)
    formal_signals = (1 if not _CONTRACTION_RE.search(message) else 0) + (
        1 if avg_sentence_len > 12 else 0
    ) + (1 if message[0].isupper() and word_count > 5 else 0)

    if casual_signals >= 2:
        formality = "casual"
    elif formal_signals >= 2:
        formality = "formal"
    else:
        formality = "neutral"

    # Emotion detection
    emotion = "neutral"
    if _FRUSTRATION_RE.search(message):
        emotion = "frustrated"
    elif has_emoji or any(w in message.lower() for w in ("thanks", "great", "love", "awesome")):
        emotion = "happy"
    elif "?" in message and word_count < 8:
        emotion = "confused"

    # Urgency
    urgency = "high" if _URGENCY_RE.search(message) else "normal"

    # Preferred length
    if word_count < 8:
        preferred_length = "short"
    elif word_count > 40:
        preferred_length = "long"
    else:
        preferred_length = "medium"

    return {
        "formality": formality,
        "emotion": emotion,
        "urgency": urgency,
        "preferred_length": preferred_length,
    }


def build_tone_instruction(tone_analysis: dict) -> str:
    formality = tone_analysis.get("formality", "neutral")
    emotion = tone_analysis.get("emotion", "neutral")
    urgency = tone_analysis.get("urgency", "normal")
    preferred_length = tone_analysis.get("preferred_length", "medium")

    parts = []
    if formality == "casual":
        parts.append("Match their casual friendly tone. Use contractions.")
    elif formality == "formal":
        parts.append("Match their formal professional tone.")
    else:
        parts.append("Use a balanced, approachable tone.")

    if emotion == "frustrated":
        parts.append("Acknowledge their frustration briefly then help.")
    if urgency == "high":
        parts.append("Be concise and direct — they're in a hurry.")
    if preferred_length == "short":
        parts.append("Keep your response to 2-3 sentences max.")
    elif preferred_length == "long":
        parts.append("Provide a thorough, detailed response.")

    return " ".join(parts)


def get_platform_personality_prompt(platform: str) -> str:
    p = PLATFORM_PERSONALITIES.get(platform, PLATFORM_PERSONALITIES["generic"])
    return (
        f"You are {p['name']} — {p['voice']}.\n"
        f"Style: {p['style']}\n"
        f"Avoid: {p['avoid']}"
    )
