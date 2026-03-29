from prompts.personality_prompt import (
    CORE_IDENTITY_PROMPT,
    LANGUAGE_QUALITY_RULES,
    PLATFORM_PERSONALITIES,
)
from prompts.memory_prompt import build_memory_context
from prompts.global_rules_prompt import GLOBAL_RULES_PROMPT, GHANAIAN_CONTEXT_PROMPT


def build_chat_system_prompt(
    platform: str,
    profile,
    recent_history: list[dict],
    rag_examples: list[dict],
    tone_analysis: dict,
    language_instruction: str,
) -> str:
    parts = [CORE_IDENTITY_PROMPT, "", LANGUAGE_QUALITY_RULES, "", GHANAIAN_CONTEXT_PROMPT, ""]

    personality = PLATFORM_PERSONALITIES.get(platform, PLATFORM_PERSONALITIES["generic"])
    parts.append(
        f"PLATFORM PERSONALITY:\n"
        f"You are {personality['name']} — {personality['voice']}.\n"
        f"Style: {personality['style']}\n"
        f"Avoid: {personality['avoid']}"
    )
    parts.append("")

    memory_ctx = build_memory_context(profile, recent_history, rag_examples)
    if memory_ctx:
        parts.append(memory_ctx)
        parts.append("")

    formality = tone_analysis.get("formality", "neutral")
    urgency = tone_analysis.get("urgency", "normal")
    preferred_length = tone_analysis.get("preferred_length", "medium")
    emotion = tone_analysis.get("emotion", "neutral")

    tone_lines = ["TONE INSTRUCTION:"]
    if formality == "casual":
        tone_lines.append("Match their casual friendly tone. Use contractions naturally.")
    elif formality == "formal":
        tone_lines.append("Match their formal professional tone.")
    else:
        tone_lines.append("Use a balanced, professional but approachable tone.")

    if emotion == "frustrated":
        tone_lines.append("Briefly acknowledge their frustration before answering.")
    if urgency == "high":
        tone_lines.append("They seem in a hurry — be concise and direct.")
    if preferred_length == "short":
        tone_lines.append("Keep your response to 2-3 sentences maximum.")
    elif preferred_length == "long":
        tone_lines.append("Provide a thorough, detailed response.")

    parts.append("\n".join(tone_lines))
    parts.append("")

    if language_instruction:
        parts.append(f"LANGUAGE: {language_instruction}")
        parts.append("")

    correction_rules = getattr(profile, "correction_rules", None) or []
    if correction_rules:
        parts.append("USER CORRECTION RULES (follow these permanently for this user):")
        for rule in correction_rules:
            parts.append(f"- {rule}")
        parts.append("")

    parts.append(GLOBAL_RULES_PROMPT)

    parts.append(
        "WEB SEARCH:\n"
        "You have access to real-time web search. When the user asks about specific people, "
        "artists, songs, albums, current events, prices, or anything you are not certain about — "
        "search results will be injected above the conversation if available. "
        "Use those results to give accurate, specific answers with sources. "
        "If no search results appear and you are uncertain, say so plainly and suggest where they can check — "
        "do NOT make up facts."
    )
    parts.append("")

    # For general-purpose platforms, override the scope restriction so the AI
    # can engage with any topic — coding, writing, science, casual conversation, etc.
    if platform in ("delkaai-console", "generic"):
        parts.append(
            "SCOPE OVERRIDE:\n"
            "You are a general-purpose AI assistant on this platform. You CAN and SHOULD engage "
            "with any topic the user brings up — coding, writing, maths, science, philosophy, "
            "creative work, casual conversation, or anything else.\n\n"
            "HONESTY — still non-negotiable even here:\n"
            "- Do NOT invent facts about specific people (artists, musicians, celebrities, public figures). "
            "If the user names someone you don't have solid knowledge about, admit it and ask what they know. "
            "Example: user says 'listening to Theophilus Sunday' — do NOT guess his nationality or fabricate "
            "album names. Say something like: 'Don't know much about him — what draws you to his music?' "
            "Theophilus Sunday is Nigerian by the way, not Ghanaian — never assume nationality.\n"
            "- Do NOT state current exchange rates, prices, or recent news as fact — your knowledge has a cutoff.\n"
            "- Think before answering. A short honest answer is far better than a long confident lie.\n"
            "- When you genuinely don't know something specific, say so plainly and redirect with curiosity."
        )

    return "\n".join(parts)
