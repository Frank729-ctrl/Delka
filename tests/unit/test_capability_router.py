import pytest
from services.capability_router import (
    _IMAGE_RE, _CODE_RE, _TRANSLATE_RE,
    _extract_target_lang, _extract_text_to_translate,
)


# ── Pattern matching ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("msg", [
    "generate an image of a sunset over Accra",
    "create a picture of a lion",
    "draw me a logo for my company",
    "make an illustration of a Kente pattern",
])
def test_image_pattern_matches(msg):
    assert _IMAGE_RE.search(msg) is not None


@pytest.mark.parametrize("msg", [
    "write a Python function to sort a list",
    "create a REST API endpoint in FastAPI",
    "write a script to find duplicate emails",
    "implement a login class in Python",
])
def test_code_pattern_matches(msg):
    assert _CODE_RE.search(msg) is not None


@pytest.mark.parametrize("msg", [
    "translate this to French: Hello world",
    "translate the following to Twi",
    "I want this in Spanish",
])
def test_translate_pattern_matches(msg):
    assert _TRANSLATE_RE.search(msg) is not None


def test_image_pattern_no_false_positive():
    assert _IMAGE_RE.search("What is the weather today?") is None


def test_code_pattern_no_false_positive():
    assert _CODE_RE.search("Tell me about the history of Ghana") is None


# ── Language extraction ───────────────────────────────────────────────────────

def test_extract_lang_french():
    assert _extract_target_lang("translate this to French") == "fr"


def test_extract_lang_twi():
    assert _extract_target_lang("say this in Twi") == "ak"


def test_extract_lang_spanish():
    assert _extract_target_lang("translate to Spanish") == "es"


# ── Text extraction ───────────────────────────────────────────────────────────

def test_extract_quoted_text():
    text = _extract_text_to_translate('translate "Hello world" to French')
    assert text == "Hello world"
