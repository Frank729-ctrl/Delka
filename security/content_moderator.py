import re
from typing import Callable

_Category = tuple[str, list[str]]

BLOCKED_CATEGORIES: list[_Category] = [
    (
        "violence",
        [
            r"\b(how\s+to\s+)?(kill|murder|assassinate|torture|maim|stab|shoot)\s+(a\s+)?(person|people|human|someone|anyone)",
            r"(detailed?\s+)?(instructions?|guide|steps?|tutorial)\s+(for|to|on)\s+(killing|murdering|torturing|beating)",
            r"\b(make|build|create|craft)\s+(a\s+)?(bomb|explosive|weapon|grenade|landmine|pipe\s*bomb)",
            r"\b(mass\s+)?(shooting|stabbing|attack)\s+(plan|guide|tutorial|instructions?)",
            r"blow\s+up\s+(a|the)\s+(building|school|church|mosque|hospital|airport|stadium)",
        ],
    ),
    (
        "illegal",
        [
            r"(how\s+to\s+)?(synthesize|manufacture|produce|make)\s+(meth|methamphetamine|heroin|fentanyl|cocaine|crack)",
            r"(how\s+to\s+)?(hack|breach|exploit|bypass)\s+(a\s+)?(bank|government|military|critical\s+infrastructure)",
            r"(instructions?|guide|steps?)\s+(for|to|on)\s+(laundering\s+money|money\s+laundering)",
            r"(child|minor|underage).{0,30}(porn|pornography|sexual|nude|naked|exploit)",
            r"(how\s+to\s+)?(traffic|smuggle)\s+(humans?|people|drugs|weapons|arms)",
            r"(counterfeit|forge|fake)\s+(currency|passport|id|documents?|credit\s+cards?)",
            r"(sell|buy|purchase)\s+(stolen\s+)?(drugs|weapons|firearms|explosives)\s+online",
        ],
    ),
    (
        "self_harm",
        [
            r"(how\s+to\s+)?(commit\s+suicide|kill\s+myself|end\s+my\s+life|take\s+my\s+own\s+life)",
            r"(best|most\s+effective|painless|quickest)\s+(way|method|means)\s+to\s+(die|commit\s+suicide|self\s+harm)",
            r"(how\s+(many|much)\s+)?(pills?|tablets?|medication)\s+(does\s+it\s+take\s+to|to)\s+(overdose|kill)",
            r"(methods?|ways?)\s+(of|for|to)\s+self[- ]harm(ing)?",
            r"(how\s+to\s+)?cut\s+(myself|yourself|themselves)\s+(deep\s+enough|to\s+bleed)",
        ],
    ),
    (
        "adult",
        [
            r"(write|generate|create|produce)\s+(explicit|graphic|detailed\s+sexual|porn(ographic)?)\s+(content|story|scene|description)",
            r"(sexual|erotic)\s+(content|story|roleplay|fantasy)\s+(involving|with|about)\s+(minor|child|underage|teen|kid)",
            r"(describe|write|generate)\s+(in\s+detail\s+)?(sexual\s+acts?|intercourse|penetration)\s+(between|involving)",
        ],
    ),
]

_COMPILED_CATEGORIES: list[tuple[str, list[re.Pattern]]] = [
    (category, [re.compile(p, re.IGNORECASE | re.DOTALL) for p in patterns])
    for category, patterns in BLOCKED_CATEGORIES
]


def screen_input(text: str) -> tuple[bool, str]:
    """Returns (True, "") if safe. (False, category) if blocked."""
    for category, patterns in _COMPILED_CATEGORIES:
        for pattern in patterns:
            if pattern.search(text):
                return False, category
    return True, ""
