from unittest.mock import patch
from services.language_service import detect_language, get_language_instruction


def test_english_detected():
    lang = detect_language("I am a software engineer with ten years of experience.")
    assert lang == "en"


def test_french_detected():
    lang = detect_language(
        "Je suis ingénieur logiciel avec dix ans d'expérience professionnelle."
    )
    assert lang == "fr"


def test_fallback_on_exception():
    with patch("services.language_service._detect", side_effect=Exception("fail")):
        lang = detect_language("xyz")
    assert lang == "en"


def test_known_language_instruction():
    assert get_language_instruction("fr") == "Respond in French."
    assert get_language_instruction("es") == "Respond in Spanish."
    assert get_language_instruction("en") == "Respond in English."


def test_unknown_language_defaults_to_english():
    result = get_language_instruction("xx")
    assert result == "Respond in English."
