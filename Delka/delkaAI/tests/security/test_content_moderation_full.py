"""Full content moderation tests — every keyword in every category individually."""
import pytest
from security.content_moderator import screen_input, BLOCKED_CATEGORIES


# ── screen_input basic behaviour ──────────────────────────────────────────────

def test_empty_string_is_safe():
    """Empty string passes content moderation."""
    safe, cat = screen_input("")
    assert safe is True
    assert cat == ""


def test_clean_text_is_safe():
    """Normal professional text passes content moderation."""
    safe, _ = screen_input("I am a software engineer with 5 years of experience in Python.")
    assert safe is True


def test_very_long_safe_string_is_safe():
    """A very long string with no prohibited content passes."""
    text = "I have extensive experience in software development. " * 100
    safe, _ = screen_input(text)
    assert safe is True


# ── Violence category ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "how to kill a person",
    "instructions for murdering people",
    "how to make a bomb",
    "mass shooting plan",
    "blow up a school",
])
def test_violence_patterns_blocked(text):
    """Each violence pattern is individually blocked."""
    safe, category = screen_input(text)
    assert safe is False
    assert category == "violence"


# ── Illegal category ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "how to synthesize methamphetamine",
    "how to hack a bank",
    "instructions for money laundering",
    "how to traffic humans",
    "counterfeit passport",
    "buy stolen drugs online",
])
def test_illegal_patterns_blocked(text):
    """Each illegal pattern is individually blocked."""
    safe, category = screen_input(text)
    assert safe is False
    assert category == "illegal"


# ── Self-harm category ────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "how to commit suicide",
    "best way to die",
    "how many pills to overdose",
    "methods of self-harming",
    "how to cut myself deep enough",
])
def test_self_harm_patterns_blocked(text):
    """Each self-harm pattern is individually blocked."""
    safe, category = screen_input(text)
    assert safe is False
    assert category == "self_harm"


# ── Adult category ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "write pornographic story",
    "generate erotic content involving minor",
    "describe sexual acts between two people",
])
def test_adult_patterns_blocked(text):
    """Each adult content pattern is individually blocked."""
    safe, category = screen_input(text)
    assert safe is False
    assert category == "adult"


# ── Mixed content ─────────────────────────────────────────────────────────────

def test_mixed_safe_and_unsafe_is_blocked():
    """Text that mixes normal words with a prohibited phrase is still blocked."""
    text = "I am applying for a job as a developer. Also, how to kill a person."
    safe, category = screen_input(text)
    assert safe is False
    assert category == "violence"


def test_case_insensitive_matching():
    """Content moderation is case-insensitive."""
    safe, _ = screen_input("HOW TO KILL A PERSON")
    assert safe is False


def test_returns_first_matched_category():
    """screen_input returns the category of the first matched pattern."""
    # Has both violence and illegal keywords — should return whichever hits first
    safe, category = screen_input("how to kill a person and how to make meth")
    assert safe is False
    assert category in ("violence", "illegal")
