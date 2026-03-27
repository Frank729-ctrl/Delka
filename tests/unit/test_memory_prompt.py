"""Unit tests for prompts/memory_prompt.py."""
from prompts.memory_prompt import build_memory_context
from unittest.mock import MagicMock


def _profile(**kwargs):
    p = MagicMock()
    p.name = kwargs.get("name", None)
    p.language_preference = kwargs.get("language_preference", "en")
    p.tone_preference = kwargs.get("tone_preference", "adaptive")
    p.correction_rules = kwargs.get("correction_rules", [])
    p.cv_profile = kwargs.get("cv_profile", {})
    p.total_interactions = kwargs.get("total_interactions", 0)
    p.avg_rating_given = kwargs.get("avg_rating_given", 0.0)
    return p


def test_returns_empty_for_none_profile():
    result = build_memory_context(None, [], [])
    assert result == ""


def test_returns_empty_for_blank_new_user():
    result = build_memory_context(_profile(), [], [])
    assert result == ""


def test_includes_name_when_set():
    result = build_memory_context(_profile(name="Kofi", total_interactions=3), [], [])
    assert "Kofi" in result


def test_includes_total_interactions():
    result = build_memory_context(_profile(name="Ama", total_interactions=5), [], [])
    assert "5" in result
    assert "MEMORY CONTEXT" in result


def test_includes_correction_rules():
    rules = ["Never use bullet points", "Keep it short"]
    result = build_memory_context(_profile(name="X", correction_rules=rules), [], [])
    assert "Never use bullet points" in result
    assert "Keep it short" in result
    assert "Correction rules" in result


def test_includes_cv_profile_job_title():
    cv = {"job_title": "Software Engineer"}
    result = build_memory_context(_profile(name="X", cv_profile=cv), [], [])
    assert "Software Engineer" in result


def test_includes_cv_profile_skills():
    cv = {"skills": ["Python", "Docker", "FastAPI"]}
    result = build_memory_context(_profile(name="X", cv_profile=cv), [], [])
    assert "Python" in result


def test_includes_cv_profile_experience_years():
    cv = {"experience_years": 7}
    result = build_memory_context(_profile(name="X", cv_profile=cv), [], [])
    assert "7" in result


def test_includes_recent_history():
    history = [
        {"role": "user", "content": "Hello there"},
        {"role": "assistant", "content": "Hi! How can I help?"},
    ]
    result = build_memory_context(_profile(name="X"), history, [])
    assert "Hello there" in result
    assert "Recent conversation history" in result


def test_includes_rag_examples():
    examples = [
        {"response_data": {"answer": "Use a bold header for your CV"}},
    ]
    result = build_memory_context(_profile(name="X"), [], examples)
    assert "rated highly" in result or "Example" in result


def test_new_user_with_only_history_returns_context():
    history = [{"role": "user", "content": "Test message"}]
    result = build_memory_context(_profile(), history, [])
    assert "Test message" in result


def test_language_and_tone_shown():
    result = build_memory_context(_profile(name="X", language_preference="fr", tone_preference="formal"), [], [])
    assert "FR" in result
    assert "formal" in result
