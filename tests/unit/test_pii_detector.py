import pytest
from security.pii_detector import detect_pii, redact


def test_detects_email():
    result = detect_pii("Contact me at frank@example.com for details.")
    assert result.found is True
    assert "email" in result.types
    assert "EMAIL_REDACTED" in result.redacted


def test_detects_phone():
    result = detect_pii("Call me on 0244123456 anytime.")
    assert result.found is True
    assert "phone" in result.types


def test_detects_credit_card():
    result = detect_pii("My card is 4111 1111 1111 1111")
    assert result.found is True
    assert "credit_card" in result.types


def test_clean_text_not_flagged():
    result = detect_pii("What is the weather in Accra today?")
    assert result.found is False
    assert result.types == []
    assert result.redacted == "What is the weather in Accra today?"


def test_redact_shortcut():
    text = "Email frank@test.com or call 0244000000"
    redacted = redact(text)
    assert "frank@test.com" not in redacted
    assert "0244000000" not in redacted


def test_multiple_pii_types():
    result = detect_pii("Email: test@test.com, Phone: +233244123456, Card: 1234-5678-9012-3456")
    assert len(result.types) >= 2
