"""Unit tests for services/personality_service.py."""
import pytest
from services.personality_service import (
    analyze_user_tone,
    build_tone_instruction,
    get_platform_personality_prompt,
)


def test_analyze_user_tone_detects_casual_short_message_with_emoji():
    result = analyze_user_tone("hey can u help me? 😊")
    assert result["formality"] == "casual"


def test_analyze_user_tone_detects_formal_from_long_structured_message():
    result = analyze_user_tone(
        "Good morning. I am writing to request assistance with the preparation "
        "of a comprehensive curriculum vitae for a senior engineering position."
    )
    assert result["formality"] == "formal"


def test_analyze_user_tone_detects_casual_contractions():
    result = analyze_user_tone("I'm not sure what I'm doing. Can't you help me?")
    assert result["formality"] == "casual"


def test_analyze_user_tone_preferred_length_short():
    result = analyze_user_tone("Help?")
    assert result["preferred_length"] == "short"


def test_analyze_user_tone_preferred_length_long():
    result = analyze_user_tone(
        " ".join(["word"] * 50)  # 50-word message
    )
    assert result["preferred_length"] == "long"


def test_analyze_user_tone_urgency_high():
    result = analyze_user_tone("I need this ASAP it is urgent!")
    assert result["urgency"] == "high"


def test_analyze_user_tone_emotion_frustrated():
    result = analyze_user_tone("This is terrible, it doesn't work!")
    assert result["emotion"] == "frustrated"


def test_build_tone_instruction_casual():
    result = build_tone_instruction({"formality": "casual", "emotion": "neutral", "urgency": "normal", "preferred_length": "medium"})
    assert "casual" in result.lower() or "contraction" in result.lower()


def test_build_tone_instruction_formal():
    result = build_tone_instruction({"formality": "formal", "emotion": "neutral", "urgency": "normal", "preferred_length": "medium"})
    assert "formal" in result.lower()


def test_build_tone_instruction_frustrated():
    result = build_tone_instruction({"formality": "neutral", "emotion": "frustrated", "urgency": "normal", "preferred_length": "medium"})
    assert "frustration" in result.lower() or "acknowledge" in result.lower()


def test_build_tone_instruction_short_preferred():
    result = build_tone_instruction({"formality": "neutral", "emotion": "neutral", "urgency": "normal", "preferred_length": "short"})
    assert "2-3" in result or "concise" in result.lower() or "short" in result.lower()


def test_get_platform_personality_prompt_swypply():
    result = get_platform_personality_prompt("swypply")
    assert "Swypply" in result or "job" in result.lower()


def test_get_platform_personality_prompt_hakdel():
    result = get_platform_personality_prompt("hakdel")
    assert "HakDel" in result or "security" in result.lower()


def test_get_platform_personality_prompt_all_platforms():
    for platform in ("swypply", "hakdel", "plugged_imports", "delkaai_docs", "generic"):
        result = get_platform_personality_prompt(platform)
        assert isinstance(result, str) and len(result) > 10


def test_get_platform_personality_prompt_falls_back_to_generic():
    result = get_platform_personality_prompt("unknown_platform_xyz")
    assert "DelkaAI" in result or "helpful" in result.lower()
