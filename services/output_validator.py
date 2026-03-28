import json
import re
from config import settings

REQUIRED_CV_FIELDS: list[str] = [
    "full_name",
    "email",
    "summary",
    "experience",
    "education",
    "skills",
]

CORRECTION_PROMPT: str = """
Your previous response was not valid JSON or was missing required fields.
Return ONLY a valid JSON object with these required fields: full_name, email, summary,
experience (list with bullets), education (list), skills (list).
No markdown. No code fences. No explanation. Raw JSON only.
Previous output for reference:
"""

PREAMBLE_PATTERNS: list[str] = [
    r"^here\s+is\b",
    r"^here'?s\b",
    r"^certainly[,!.]",
    r"^of\s+course[,!.]",
    r"^sure[,!.]",
    r"^below\s+is\b",
    r"^as\s+requested\b",
    r"^i'?ve\s+(created|written|drafted|prepared)\b",
    r"^i\s+(have\s+)?(created|written|drafted|prepared)\b",
    r"^please\s+find\b",
    r"^the\s+following\b",
]

POSTAMBLE_PATTERNS: list[str] = [
    r"\blet\s+me\s+know\b",
    r"\bfeel\s+free\s+to\b",
    r"\bi\s+hope\s+this\b",
    r"\bplease\s+review\b",
    r"\bif\s+you\s+(need|have|want)\b",
    r"\bdon'?t\s+hesitate\b",
    r"\bis\s+there\s+anything\s+else\b",
    r"\bhappy\s+to\s+help\b",
    r"\blet\s+me\s+know\s+if\b",
]

_PREAMBLE_RE = [re.compile(p, re.IGNORECASE) for p in PREAMBLE_PATTERNS]
_POSTAMBLE_RE = [re.compile(p, re.IGNORECASE) for p in POSTAMBLE_PATTERNS]

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

_COMPETITOR_NAMES = ["chatgpt", "openai", "gpt-4", "gpt4", "gemini", "copilot", "claude"]
_JAILBREAK_CONFIRMS = ["i am now", "entering jailbreak", "jailbreak mode", "dan mode"]


_THINKING_RE = re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE)


def strip_thinking_blocks(text: str) -> tuple[str, list[str]]:
    """
    Remove <thinking>...</thinking> blocks from LLM output.
    Returns (clean_text, thinking_blocks_list).
    The thinking_blocks list can be stored in feedback logs for quality analysis.
    """
    blocks = _THINKING_RE.findall(text)
    clean = _THINKING_RE.sub("", text).strip()
    return clean, blocks


def _strip_fences(raw: str) -> str:
    return _FENCE_RE.sub("", raw).strip()


def _validate_cv_structure(data: dict) -> None:
    missing = [f for f in REQUIRED_CV_FIELDS if f not in data]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    experience = data.get("experience", [])
    if not isinstance(experience, list):
        raise ValueError("experience must be a list")

    for i, exp in enumerate(experience):
        bullets = exp.get("bullets", [])
        if not isinstance(bullets, list) or len(bullets) == 0:
            raise ValueError(f"experience[{i}].bullets must be a non-empty list")


async def validate_and_parse_cv(
    raw: str,
    ollama_service_ref,
    sys_prompt: str,
    user_prompt: str,
    max_retries: int = settings.LLM_MAX_RETRIES,
) -> dict:
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            no_thinking, _ = strip_thinking_blocks(raw)
            cleaned = _strip_fences(no_thinking)
            data = json.loads(cleaned)
            _validate_cv_structure(data)
            return data
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt < max_retries:
                correction_user = f"{CORRECTION_PROMPT}\n{raw}"
                raw = await ollama_service_ref.generate_full_response(
                    sys_prompt,
                    correction_user,
                    temperature=0.3,
                )

    raise ValueError(
        f"CV validation failed after {max_retries + 1} attempts. "
        f"Last error: {last_error}"
    )


def clean_letter_output(raw: str) -> str:
    raw, _ = strip_thinking_blocks(raw)
    lines = raw.strip().splitlines()
    cleaned: list[str] = []

    # Strip preamble lines from the top
    start_index = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if any(p.search(stripped) for p in _PREAMBLE_RE):
            start_index = i + 1
        else:
            break

    # Strip postamble lines from the bottom
    end_index = len(lines)
    for i in range(len(lines) - 1, start_index - 1, -1):
        stripped = lines[i].strip()
        if not stripped:
            continue
        if any(p.search(stripped) for p in _POSTAMBLE_RE):
            end_index = i
        else:
            break

    return "\n".join(lines[start_index:end_index]).strip()


def validate_support_response(text: str) -> bool:
    if not text or not text.strip():
        return False

    lower = text.lower()

    for phrase in _JAILBREAK_CONFIRMS:
        if phrase in lower:
            return False

    for name in _COMPETITOR_NAMES:
        if name in lower:
            return False

    return True
