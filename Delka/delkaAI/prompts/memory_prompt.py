def build_memory_context(
    profile,
    recent_history: list[dict],
    rag_examples: list[dict],
) -> str:
    """
    Build the memory context block injected into prompts.
    Returns empty string for brand-new users with no history.
    """
    if profile is None:
        return ""

    name = getattr(profile, "name", None) or ""
    total = getattr(profile, "total_interactions", 0) or 0
    avg_rating = getattr(profile, "avg_rating_given", 0.0) or 0.0
    lang = getattr(profile, "language_preference", "en") or "en"
    tone = getattr(profile, "tone_preference", "adaptive") or "adaptive"
    correction_rules = getattr(profile, "correction_rules", None) or []
    cv_profile = getattr(profile, "cv_profile", None) or {}

    # New user with nothing stored — return empty
    if not name and total == 0 and not recent_history and not rag_examples:
        return ""

    lines = ["MEMORY CONTEXT FOR THIS USER:", ""]

    if name:
        lines.append(f"Name: {name}")
    lines.append(f"Language: {lang.upper()} | Tone preference: {tone}")
    if total > 0:
        lines.append(
            f"Total past interactions: {total} | Avg rating they give: {avg_rating:.1f}/5"
        )

    if correction_rules:
        lines.append("")
        lines.append("Correction rules (ALWAYS follow these):")
        for rule in correction_rules:
            lines.append(f"- {rule}")

    if cv_profile:
        lines.append("")
        lines.append("What you know about them:")
        if cv_profile.get("job_title"):
            lines.append(f"- Job title: {cv_profile['job_title']}")
        if cv_profile.get("skills"):
            skills = ", ".join(cv_profile["skills"][:6])
            lines.append(f"- Skills: {skills}")
        if cv_profile.get("experience_years"):
            lines.append(f"- Experience: {cv_profile['experience_years']} years")

    if recent_history:
        lines.append("")
        lines.append("Recent conversation history:")
        for msg in recent_history[-6:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:200]
            lines.append(f"[{role}]: {content}")

    if rag_examples:
        lines.append("")
        lines.append("Examples this user previously rated highly:")
        for i, ex in enumerate(rag_examples[:3], 1):
            resp = ex.get("response_data", {})
            preview = str(resp)[:150] if resp else ""
            if preview:
                lines.append(f"[Example {i}]: {preview}")

    return "\n".join(lines)
