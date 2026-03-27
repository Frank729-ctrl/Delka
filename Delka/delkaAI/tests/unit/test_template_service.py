from services.template_service import (
    pick_random_cv_template,
    pick_random_letter_template,
    CV_TEMPLATES,
    LETTER_TEMPLATES,
    COLOR_SCHEMES,
)


def test_cv_template_returns_valid_name_and_dict():
    name, color = pick_random_cv_template()
    assert name in CV_TEMPLATES
    assert isinstance(color, dict)


def test_letter_template_returns_valid_name_and_dict():
    name, color = pick_random_letter_template()
    assert name in LETTER_TEMPLATES
    assert isinstance(color, dict)


def test_color_dict_has_required_keys():
    for scheme_name, scheme in COLOR_SCHEMES.items():
        for key in ("primary", "secondary", "accent", "text"):
            assert key in scheme, f"Scheme '{scheme_name}' missing key '{key}'"


def test_muted_scheme_exists():
    assert "muted" in COLOR_SCHEMES
    assert len(COLOR_SCHEMES) >= 6
