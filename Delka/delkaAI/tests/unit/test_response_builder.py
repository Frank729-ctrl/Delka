"""Tests for utils/response_builder.py — covers all branches of build_success/build_error."""
import pytest
from utils.response_builder import build_success, build_error


def test_build_success_defaults():
    """build_success with no args returns correct structure."""
    r = build_success()
    assert r["status"] == "success"
    assert r["message"] == "success"
    assert r["data"] is None


def test_build_success_with_data():
    """build_success with data payload includes it in response."""
    payload = {"id": 1, "name": "test"}
    r = build_success(data=payload)
    assert r["status"] == "success"
    assert r["data"] == payload


def test_build_success_with_custom_message():
    """build_success with custom message uses that message."""
    r = build_success(message="Key created.", data={"key": "sk-xxx"})
    assert r["message"] == "Key created."
    assert r["data"]["key"] == "sk-xxx"


def test_build_error_defaults():
    """build_error with only message returns correct error structure."""
    r = build_error(message="Something went wrong")
    assert r["status"] == "error"
    assert r["message"] == "Something went wrong"
    assert r["data"] is None


def test_build_error_with_request_id():
    """build_error with request_id includes it in data dict."""
    rid = "abc-123"
    r = build_error(message="Not found", request_id=rid)
    assert r["status"] == "error"
    assert r["data"] == {"request_id": rid}


def test_build_error_without_request_id_data_is_none():
    """build_error without request_id has data=None (not empty dict)."""
    r = build_error(message="oops")
    assert r["data"] is None


def test_build_success_and_error_always_have_status():
    """Both builders always include a status field."""
    assert "status" in build_success()
    assert "status" in build_error()
