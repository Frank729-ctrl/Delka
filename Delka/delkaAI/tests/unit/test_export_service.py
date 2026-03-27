"""Tests for services/export_service.py — all templates, color schemes, edge cases."""
import pytest
from services.export_service import render_cv_to_pdf, render_letter_to_pdf
from services.template_service import COLOR_SCHEMES


# ── Minimal CV data fixture ──────────────────────────────────────────────────

_MINIMAL_CV = {
    "full_name": "Jane Smith",
    "email": "jane@example.com",
    "phone": "+1234567890",
    "location": "London, UK",
    "summary": "Experienced engineer.",
    "experience": [
        {
            "company": "TechCorp",
            "title": "Senior Engineer",
            "start_date": "2019-01",
            "end_date": "Present",
            "bullets": ["Led team", "Built APIs"],
        }
    ],
    "education": [
        {"school": "MIT", "degree": "BSc", "field": "CS", "year": "2016"}
    ],
    "skills": ["Python", "Docker"],
}

_MINIMAL_LETTER = {
    "applicant_name": "Jane Smith",
    "company_name": "Acme Corp",
    "job_title": "Engineer",
    "job_description": "Build things",
    "applicant_background": "10 years experience.",
}

_BLUE = COLOR_SCHEMES["professional_blue"]


# ── CV template tests ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("template", [
    "modern_sidebar",
    "minimal_clean",
    "bold_header",
    "timeline_style",
    "executive_classic",
])
def test_cv_template_renders_to_pdf(template):
    """Each of the 5 CV templates renders to valid PDF bytes."""
    result = render_cv_to_pdf(_MINIMAL_CV, template, _BLUE)
    assert isinstance(result, bytes)
    assert result.startswith(b"%PDF")
    assert len(result) > 100


# ── Cover letter template tests ───────────────────────────────────────────────

@pytest.mark.parametrize("template", [
    "letterhead_style",
    "modern_block",
    "clean_minimal",
])
def test_letter_template_renders_to_pdf(template):
    """Each of the 3 cover letter templates renders to valid PDF bytes."""
    result = render_letter_to_pdf(
        "This is my cover letter.\n\nSecond paragraph here.",
        _MINIMAL_LETTER,
        template,
        _BLUE,
    )
    assert isinstance(result, bytes)
    assert result.startswith(b"%PDF")
    assert len(result) > 100


# ── Color scheme tests ────────────────────────────────────────────────────────

@pytest.mark.parametrize("color_key", list(COLOR_SCHEMES.keys()))
def test_cv_all_color_schemes_render(color_key):
    """Each of the 6 color schemes applies without error."""
    color = COLOR_SCHEMES[color_key]
    result = render_cv_to_pdf(_MINIMAL_CV, "bold_header", color)
    assert result.startswith(b"%PDF")


# ── Edge case tests ───────────────────────────────────────────────────────────

def test_cv_missing_optional_phone_renders():
    """CV without optional phone field renders gracefully."""
    cv = dict(_MINIMAL_CV)
    cv.pop("phone", None)
    result = render_cv_to_pdf(cv, "minimal_clean", _BLUE)
    assert result.startswith(b"%PDF")


def test_cv_missing_optional_location_renders():
    """CV without optional location field renders gracefully."""
    cv = dict(_MINIMAL_CV)
    cv.pop("location", None)
    result = render_cv_to_pdf(cv, "minimal_clean", _BLUE)
    assert result.startswith(b"%PDF")


def test_cv_empty_skills_list_renders():
    """CV with empty skills list renders without error."""
    cv = dict(_MINIMAL_CV)
    cv["skills"] = []
    result = render_cv_to_pdf(cv, "bold_header", _BLUE)
    assert result.startswith(b"%PDF")


def test_cv_empty_experience_renders():
    """CV with no experience entries renders without error."""
    cv = dict(_MINIMAL_CV)
    cv["experience"] = []
    result = render_cv_to_pdf(cv, "bold_header", _BLUE)
    assert result.startswith(b"%PDF")


def test_letter_multi_paragraph_renders():
    """Cover letter with multiple paragraphs renders correctly."""
    letter_text = "\n\n".join([f"Paragraph {i} here." for i in range(5)])
    result = render_letter_to_pdf(letter_text, _MINIMAL_LETTER, "modern_block", _BLUE)
    assert result.startswith(b"%PDF")


def test_letter_single_paragraph_renders():
    """Cover letter with a single paragraph (no double newline) renders."""
    result = render_letter_to_pdf("Just one paragraph.", _MINIMAL_LETTER, "clean_minimal", _BLUE)
    assert result.startswith(b"%PDF")
