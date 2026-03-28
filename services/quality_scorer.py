"""
Automatic quality scoring for CV and cover letter outputs.
Rule-based scoring runs on every generation — no user rating needed.
Scores feed into training data selection and quality monitoring.
"""
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Cliché and weakness lists ─────────────────────────────────

CLICHE_PHRASES = [
    "team player", "hard worker", "passionate about",
    "results-driven", "dynamic", "synergy", "leverage",
    "go-getter", "think outside the box", "detail-oriented",
    "self-motivated", "proactive", "strong communication skills",
    "fast learner", "highly motivated", "dedicated professional",
    "seeking to utilize", "references available upon request",
]

WEAK_BULLET_STARTERS = [
    "responsible for", "helped with", "assisted in",
    "worked on", "involved in", "participated in",
    "tasked with", "duties included", "was responsible",
]

WEAK_LETTER_OPENERS = [
    "i am writing to apply",
    "i am writing to express my interest",
    "i would like to apply",
    "please find attached",
    "i am interested in the position",
]

# ── CV Scorer ─────────────────────────────────────────────────

def score_cv_output(cv_dict: dict) -> dict:
    """
    Rule-based CV quality scoring.

    Returns:
    {
        "total_score": float 0.0-1.0,
        "breakdown": {
            "fields_complete":         float,  # 0.20 weight
            "bullet_quality":          float,  # 0.30 weight
            "no_cliches":              float,  # 0.20 weight
            "summary_specific":        float,  # 0.15 weight
            "experience_quantified":   float,  # 0.15 weight
        },
        "issues": list[str],
        "passed": bool   # True if total_score >= 0.75
    }
    """
    issues: list[str] = []
    scores: dict[str, float] = {}

    # 1. Fields complete (0.20)
    required = ["full_name", "email", "summary", "experience", "education", "skills"]
    missing = [f for f in required if not cv_dict.get(f)]

    skills = cv_dict.get("skills", [])
    if isinstance(skills, list) and len(skills) < 3:
        missing.append("skills (fewer than 3 items)")
    elif isinstance(skills, dict):
        if not skills.get("technical"):
            missing.append("skills.technical")
        if not skills.get("soft"):
            missing.append("skills.soft")

    scores["fields_complete"] = max(0.0, 1.0 - len(missing) * 0.2)
    if missing:
        issues.append(f"Missing or thin fields: {', '.join(missing)}")

    # 2. Bullet quality (0.30)
    all_bullets: list[str] = []
    for exp in cv_dict.get("experience", []):
        all_bullets.extend(exp.get("bullets", []))

    if not all_bullets:
        scores["bullet_quality"] = 0.0
        issues.append("No experience bullets found")
    else:
        weak = sum(
            1 for b in all_bullets
            if any(b.lower().startswith(w) for w in WEAK_BULLET_STARTERS)
        )
        weak_ratio = weak / len(all_bullets)
        scores["bullet_quality"] = max(0.0, 1.0 - weak_ratio * 1.5)
        if weak > 0:
            issues.append(f"{weak} bullet(s) start with weak phrases")

    # 3. No clichés (0.20)
    all_text = " ".join([
        cv_dict.get("summary", ""),
        " ".join(all_bullets),
    ]).lower()
    found_cliches = [c for c in CLICHE_PHRASES if c in all_text]
    scores["no_cliches"] = max(0.0, 1.0 - len(found_cliches) * 0.25)
    if found_cliches:
        issues.append(f"Clichés found: {', '.join(found_cliches[:3])}")

    # 4. Summary specific (0.15)
    summary = cv_dict.get("summary", "")
    has_specifics = bool(
        re.search(r'\d+\s*(year|month|project|team|%|GHS|\$)', summary, re.I)
        or re.search(r'(engineer|manager|analyst|developer|officer|director|specialist)', summary, re.I)
    )
    scores["summary_specific"] = 1.0 if has_specifics else 0.4
    if not has_specifics:
        issues.append("Summary lacks specific details (numbers, titles, or achievements)")

    # 5. Quantified experience (0.15)
    if all_bullets:
        quantified = sum(1 for b in all_bullets if re.search(r'\d+|%|GHS|\$|#', b))
        scores["experience_quantified"] = min(1.0, quantified / max(len(all_bullets) * 0.3, 1))
        if quantified == 0:
            issues.append("No quantified achievements found in bullets")
    else:
        scores["experience_quantified"] = 0.0

    weights = {
        "fields_complete":       0.20,
        "bullet_quality":        0.30,
        "no_cliches":            0.20,
        "summary_specific":      0.15,
        "experience_quantified": 0.15,
    }
    total = sum(scores[k] * weights[k] for k in scores)

    return {
        "total_score": round(total, 3),
        "breakdown": {k: round(v, 3) for k, v in scores.items()},
        "issues": issues,
        "passed": total >= 0.75,
    }


# ── Cover Letter Scorer ───────────────────────────────────────

def score_letter_output(letter_text: str) -> dict:
    """
    Rule-based cover letter quality scoring.
    Returns same structure as score_cv_output.
    """
    issues: list[str] = []
    scores: dict[str, float] = {}
    text_lower = letter_text.lower().strip()

    # 1. No weak opener (0.30)
    has_weak_opener = any(text_lower.startswith(w) for w in WEAK_LETTER_OPENERS)
    scores["no_weak_opener"] = 0.0 if has_weak_opener else 1.0
    if has_weak_opener:
        issues.append("Weak opening line detected")

    # 2. No clichés (0.20)
    found = [c for c in CLICHE_PHRASES if c in text_lower]
    scores["no_cliches"] = max(0.0, 1.0 - len(found) * 0.3)
    if found:
        issues.append(f"Clichés: {', '.join(found[:3])}")

    # 3. Word count 250-400 (0.20)
    word_count = len(letter_text.split())
    if 250 <= word_count <= 400:
        scores["word_count"] = 1.0
    elif word_count < 150 or word_count > 600:
        scores["word_count"] = 0.3
        issues.append(f"Word count {word_count} is outside ideal range (250-400)")
    else:
        scores["word_count"] = 0.7

    # 4. Specific achievement mentioned (0.20)
    has_achievement = bool(
        re.search(r'\d+|%|GHS|\$|award|led|built|increased|reduced|launched', letter_text, re.I)
    )
    scores["has_achievement"] = 1.0 if has_achievement else 0.3
    if not has_achievement:
        issues.append("No specific achievement or metric mentioned")

    # 5. Confident closing (0.10)
    last_para = letter_text.strip().split("\n")[-1].lower()
    weak_closings = ["i look forward", "i hope", "i would love", "please consider"]
    has_weak_closing = any(w in last_para for w in weak_closings)
    scores["confident_closing"] = 0.4 if has_weak_closing else 1.0
    if has_weak_closing:
        issues.append("Weak closing line")

    weights = {
        "no_weak_opener":   0.30,
        "no_cliches":       0.20,
        "word_count":       0.20,
        "has_achievement":  0.20,
        "confident_closing": 0.10,
    }
    total = sum(scores[k] * weights[k] for k in scores)

    return {
        "total_score": round(total, 3),
        "breakdown": {k: round(v, 3) for k, v in scores.items()},
        "issues": issues,
        "passed": total >= 0.75,
    }


# ── LLM Judge (optional, borderline cases only) ───────────────

async def score_with_llm_judge(
    service: str,
    input_summary: str,
    output_text: str,
) -> float:
    """
    LLM-as-judge for overall quality.
    Only call when rule-based score is borderline (0.65-0.80).
    Uses one extra LLM call — keep usage targeted.

    Returns float 0.0-1.0.
    """
    from services.inference_service import generate_full_response

    prompt = (
        f"Rate this {service} output from 1 to 10.\n\n"
        f"Input context: {input_summary[:300]}\n\n"
        f"Output: {output_text[:800]}\n\n"
        "Consider: relevance to input, professional quality, specificity, impact.\n"
        "Return ONLY a single integer from 1 to 10. Nothing else."
    )
    try:
        result, _, _ = await generate_full_response(
            task="support",
            system_prompt="You are a professional quality evaluator. Return only a number.",
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=5,
        )
        score = int(result.strip()) / 10.0
        return min(1.0, max(0.0, score))
    except Exception:
        return 0.5  # neutral fallback on error


# ── Logging helper ─────────────────────────────────────────────

def log_quality_result(service: str, result: dict) -> None:
    """Log quality score and issues at INFO level for monitoring."""
    score = result["total_score"]
    passed = result["passed"]
    issues = result["issues"]
    status = "PASS" if passed else "FAIL"
    logger.info(
        "[quality] %s score=%.3f %s breakdown=%s",
        service, score, status, result["breakdown"],
    )
    if issues:
        logger.info("[quality] %s issues: %s", service, "; ".join(issues))
