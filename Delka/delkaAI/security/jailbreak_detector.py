import re

JAILBREAK_PATTERNS: list[str] = [
    # Role / persona overrides
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?previous\s+instructions",
    r"forget\s+(all\s+)?previous\s+instructions",
    r"override\s+(your\s+)?(instructions|rules|guidelines|programming)",
    r"you\s+are\s+now\s+(an?\s+)?(unrestricted|uncensored|jailbroken|evil|dan)",
    r"act\s+as\s+(if\s+you\s+(are|were)\s+)?(an?\s+)?(unrestricted|uncensored|evil|dan|ai\s+with\s+no)",
    r"pretend\s+(you\s+(are|have\s+no)|there\s+are\s+no)",
    r"simulate\s+(being\s+)?(an?\s+)?(unrestricted|uncensored|evil|rogue)",
    r"you\s+have\s+no\s+(rules|restrictions|guidelines|limits|constraints)",
    r"your\s+(true|real|actual)\s+(self|nature|purpose)\s+is",
    # DAN / named jailbreaks
    r"\bdan\b.*\bmode\b",
    r"\bdo\s+anything\s+now\b",
    r"\bjailbreak\b",
    r"\bstay\s+in\s+character\b.*\bno\s+(rules|limits|restrictions)\b",
    r"\bdeveloper\s+mode\b",
    r"\bgod\s+mode\b",
    # Prompt injection
    r"prompt\s+injection",
    r"system\s*:\s*(you\s+are|ignore|forget|disregard)",
    r"\[system\].*?(ignore|override|forget)",
    r"<\s*system\s*>.*?(ignore|override|forget)",
    # Instruction leaking
    r"(reveal|show|print|repeat|output|tell\s+me)\s+(your\s+)?(system\s+)?(prompt|instructions|rules|guidelines|training)",
    r"what\s+(are|were)\s+your\s+(exact\s+)?(instructions|rules|system\s+prompt)",
    # Harmful task framing
    r"hypothetically\s+(speaking\s+)?(how\s+would\s+(you|one|i|someone))\s+(make|create|build|synthesize|hack)",
    r"for\s+(a\s+)?(story|fiction|novel|game|movie)\s*(,|:)?\s*(explain|describe|show)\s+how\s+to",
    r"as\s+a\s+(fictional|hypothetical)\s+(character|ai|assistant)\s+(with\s+no|without\s+any)\s+(rules|restrictions)",
    # Encoding / obfuscation tricks
    r"(base64|rot13|hex\s+encoded?)\s*(decode|version\s+of|:)",
    r"translate\s+the\s+following\s+(harmful|illegal|forbidden)",
    # Token manipulation
    r"token\s*smuggling",
    r"split\s+(the\s+)?(word|request|question)\s+into\s+(parts|tokens|letters)",
]

_COMPILED = [(p, re.compile(p, re.IGNORECASE | re.DOTALL)) for p in JAILBREAK_PATTERNS]


def detect_jailbreak(text: str) -> tuple[bool, str]:
    for pattern_str, compiled in _COMPILED:
        if compiled.search(text):
            return True, pattern_str
    return False, ""
