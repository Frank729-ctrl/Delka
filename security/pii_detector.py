"""
PII (Personally Identifiable Information) detector.
Uses regex patterns for fast detection, with NVIDIA safety model as enhancement.
Detected PII types: email, phone, national ID, credit card, SSN, passport.
"""
import re
from typing import List


_PII_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone": re.compile(r"\b(?:\+?233|0)?[2-9]\d{8}\b|\b\+?[1-9]\d{6,14}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "ghana_voter_id": re.compile(r"\b[A-Z]{2}\d{7}\b"),
    "passport": re.compile(r"\bG\d{7}\b"),  # Ghana passport format
    "ssn_us": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "national_id": re.compile(r"\bGHA-\d{9}-\d\b"),
}


class PIIResult:
    def __init__(self, found: bool, types: List[str], redacted: str):
        self.found = found
        self.types = types
        self.redacted = redacted


def detect_pii(text: str) -> PIIResult:
    """
    Scan text for PII. Returns PIIResult with found flag, types list, and redacted version.
    """
    found_types = []
    redacted = text

    for pii_type, pattern in _PII_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            found_types.append(pii_type)
            # Replace each match with a placeholder
            placeholder = f"[{pii_type.upper()}_REDACTED]"
            redacted = pattern.sub(placeholder, redacted)

    return PIIResult(
        found=bool(found_types),
        types=found_types,
        redacted=redacted,
    )


def redact(text: str) -> str:
    """Quick redact — returns text with all PII replaced."""
    return detect_pii(text).redacted
