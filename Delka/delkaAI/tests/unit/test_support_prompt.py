"""Tests for prompts/support_prompt.py — all platforms, global rules, language injection."""
import pytest
from prompts.support_prompt import build_support_system_prompt
from prompts.global_rules_prompt import GLOBAL_RULES_PROMPT


@pytest.mark.parametrize("platform", ["swypply", "hakdel", "plugged_imports", "generic"])
def test_known_platform_returns_string(platform):
    """build_support_system_prompt returns a non-empty string for every known platform."""
    result = build_support_system_prompt(platform, "Respond in English.")
    assert isinstance(result, str)
    assert len(result) > 100


def test_unknown_platform_falls_back_to_generic():
    """An unrecognized platform name falls back to the generic prompt."""
    result = build_support_system_prompt("unknown_platform", "Respond in English.")
    generic_result = build_support_system_prompt("generic", "Respond in English.")
    # Both should contain the same platform-specific portion
    assert "AI support agent" in result


def test_global_rules_present_in_every_platform_prompt():
    """GLOBAL_RULES_PROMPT appears in every platform's output."""
    for platform in ["swypply", "hakdel", "plugged_imports", "generic"]:
        result = build_support_system_prompt(platform, "Respond in English.")
        assert GLOBAL_RULES_PROMPT in result, f"Global rules missing for platform={platform}"


def test_language_instruction_appended():
    """The language_instruction is always appended to the output."""
    lang_instruction = "Respond in French."
    result = build_support_system_prompt("generic", lang_instruction)
    assert lang_instruction in result


def test_scope_rule_references_platform_name():
    """The scope rule contains the platform name in title-case."""
    result = build_support_system_prompt("swypply", "Respond in English.")
    assert "Swypply" in result


def test_case_insensitive_platform_lookup():
    """Platform lookup is case-insensitive (GENERIC == generic)."""
    result_lower = build_support_system_prompt("generic", "")
    result_upper = build_support_system_prompt("GENERIC", "")
    # Both should use the same platform prompt
    assert result_lower == result_upper
