import json
import pytest
from services.output_validator import (
    validate_and_parse_cv,
    clean_letter_output,
    validate_support_response,
    REQUIRED_CV_FIELDS,
)

_VALID_CV = {
    "full_name": "Jane Smith",
    "email": "jane@example.com",
    "summary": "Great engineer.",
    "experience": [
        {
            "company": "Acme",
            "title": "Engineer",
            "start_date": "2020",
            "end_date": "Present",
            "bullets": ["Did good work"],
        }
    ],
    "education": [{"school": "MIT", "degree": "BSc", "field": "CS", "year": "2018"}],
    "skills": ["Python"],
}


class _FakeOllama:
    async def generate_full_response(self, *args, **kwargs):
        return json.dumps(_VALID_CV)


async def test_valid_json_passes():
    result = await validate_and_parse_cv(
        json.dumps(_VALID_CV), _FakeOllama(), "sys", "usr"
    )
    assert result["full_name"] == "Jane Smith"


async def test_missing_required_fields_raises():
    bad = {"full_name": "X", "email": "x@x.com"}
    with pytest.raises(ValueError, match="Missing required fields"):
        await validate_and_parse_cv(json.dumps(bad), _FakeOllama(), "sys", "usr", max_retries=0)


async def test_empty_bullets_raises():
    bad = dict(_VALID_CV)
    bad["experience"] = [
        {"company": "A", "title": "B", "start_date": "2020", "end_date": "Now", "bullets": []}
    ]
    with pytest.raises(ValueError):
        await validate_and_parse_cv(json.dumps(bad), _FakeOllama(), "sys", "usr", max_retries=0)


async def test_json_fences_stripped():
    fenced = f"```json\n{json.dumps(_VALID_CV)}\n```"
    result = await validate_and_parse_cv(fenced, _FakeOllama(), "sys", "usr")
    assert result["email"] == "jane@example.com"


def test_clean_letter_strips_preamble():
    raw = "Here is the letter you requested:\n\nWith great enthusiasm I apply."
    cleaned = clean_letter_output(raw)
    assert not cleaned.lower().startswith("here is")
    assert "enthusiasm" in cleaned


def test_clean_letter_strips_postamble():
    raw = "I look forward to hearing from you.\n\nLet me know if you need anything else."
    cleaned = clean_letter_output(raw)
    assert "let me know" not in cleaned.lower()


def test_validate_support_response_empty_fails():
    assert validate_support_response("") is False
    assert validate_support_response("   ") is False


def test_validate_support_response_competitor_fails():
    assert validate_support_response("You should use ChatGPT instead.") is False


def test_validate_support_response_valid_passes():
    assert validate_support_response("I can help you with that question.") is True
