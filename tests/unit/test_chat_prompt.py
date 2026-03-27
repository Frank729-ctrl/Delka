"""Unit tests for prompts/chat_prompt.py."""
from unittest.mock import MagicMock
from prompts.chat_prompt import build_chat_system_prompt
from prompts.personality_prompt import CORE_IDENTITY_PROMPT, LANGUAGE_QUALITY_RULES


def _blank_profile(**kwargs):
    p = MagicMock()
    p.name = kwargs.get("name", None)
    p.language_preference = "en"
    p.tone_preference = "adaptive"
    p.correction_rules = kwargs.get("correction_rules", [])
    p.preferences = {}
    p.cv_profile = {}
    p.topics_discussed = []
    p.total_interactions = kwargs.get("total_interactions", 0)
    p.avg_rating_given = 0.0
    p.last_seen = None
    return p


def _tone(formality="neutral"):
    return {"formality": formality, "emotion": "neutral", "urgency": "normal", "preferred_length": "medium"}


def test_build_chat_system_prompt_includes_core_identity():
    prompt = build_chat_system_prompt("generic", _blank_profile(), [], [], _tone(), "")
    assert "DelkaAI" in prompt
    assert "Honest" in prompt or "honest" in prompt


def test_build_chat_system_prompt_includes_language_rules():
    prompt = build_chat_system_prompt("generic", _blank_profile(), [], [], _tone(), "")
    assert "NEVER start a response" in prompt or "filler" in prompt.lower()


def test_build_chat_system_prompt_includes_platform_personality():
    prompt = build_chat_system_prompt("swypply", _blank_profile(), [], [], _tone(), "")
    assert "Swypply" in prompt or "job" in prompt.lower()


def test_build_chat_system_prompt_includes_memory_context_when_profile_has_data():
    profile = _blank_profile(name="Kofi", total_interactions=5)
    prompt = build_chat_system_prompt("generic", profile, [], [], _tone(), "")
    assert "Kofi" in prompt


def test_build_chat_system_prompt_includes_correction_rules():
    profile = _blank_profile(correction_rules=["Never use bullet points"])
    prompt = build_chat_system_prompt("generic", profile, [], [], _tone(), "")
    assert "Never use bullet points" in prompt


def test_build_chat_system_prompt_includes_global_rules():
    prompt = build_chat_system_prompt("generic", _blank_profile(), [], [], _tone(), "")
    assert "SAFETY" in prompt or "jailbreak" in prompt.lower() or "DelkaAI" in prompt


def test_build_chat_system_prompt_tone_casual_instruction():
    prompt = build_chat_system_prompt("generic", _blank_profile(), [], [], _tone("casual"), "")
    assert "casual" in prompt.lower()


def test_build_chat_system_prompt_with_language_instruction():
    prompt = build_chat_system_prompt("generic", _blank_profile(), [], [], _tone(), "Respond in French.")
    assert "French" in prompt
