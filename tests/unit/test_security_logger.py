"""Tests for security/security_logger.py — log_security_event + get_recent_events."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from security.security_logger import log_security_event, get_recent_events, _sanitize


# ── _sanitize tests ───────────────────────────────────────────────────────────

def test_sanitize_redacts_sensitive_keys():
    """_sanitize redacts keys in the sensitive keys set."""
    details = {"raw_key": "sk-abc", "password": "hunter2", "token": "xyz"}
    result = _sanitize(details)
    assert result["raw_key"] == "[REDACTED]"
    assert result["password"] == "[REDACTED]"
    assert result["token"] == "[REDACTED]"


def test_sanitize_keeps_safe_keys():
    """_sanitize preserves non-sensitive keys unchanged."""
    details = {"ip": "1.2.3.4", "platform": "swypply"}
    result = _sanitize(details)
    assert result["ip"] == "1.2.3.4"
    assert result["platform"] == "swypply"


def test_sanitize_truncates_input_preview():
    """_sanitize truncates input_preview strings to 200 chars."""
    details = {"input_preview": "x" * 300}
    result = _sanitize(details)
    assert len(result["input_preview"]) == 200


def test_sanitize_input_preview_short_string_unchanged():
    """_sanitize does not truncate input_preview below 200 chars."""
    details = {"input_preview": "short"}
    result = _sanitize(details)
    assert result["input_preview"] == "short"


# ── log_security_event routing tests ─────────────────────────────────────────

def test_log_security_event_critical(monkeypatch):
    """CRITICAL severity calls security_logger_instance.critical()."""
    mock_logger = MagicMock()
    monkeypatch.setattr("security.security_logger.security_logger_instance", mock_logger)
    log_security_event("CRITICAL", "honeypot_triggered", {"ip": "1.2.3.4"})
    mock_logger.critical.assert_called_once()


def test_log_security_event_error(monkeypatch):
    """ERROR severity calls security_logger_instance.error()."""
    mock_logger = MagicMock()
    monkeypatch.setattr("security.security_logger.security_logger_instance", mock_logger)
    log_security_event("ERROR", "db_error", {"detail": "timeout"})
    mock_logger.error.assert_called_once()


def test_log_security_event_warning(monkeypatch):
    """WARNING severity calls security_logger_instance.warning()."""
    mock_logger = MagicMock()
    monkeypatch.setattr("security.security_logger.security_logger_instance", mock_logger)
    log_security_event("WARNING", "rate_limited", {"key": "fd-delka-sk-abc"})
    mock_logger.warning.assert_called_once()


def test_log_security_event_info(monkeypatch):
    """INFO (default) severity calls security_logger_instance.info()."""
    mock_logger = MagicMock()
    monkeypatch.setattr("security.security_logger.security_logger_instance", mock_logger)
    log_security_event("INFO", "key_created", {"platform": "test"})
    mock_logger.info.assert_called_once()


def test_log_security_event_unknown_severity_falls_back_to_info(monkeypatch):
    """Unrecognized severity level falls back to info()."""
    mock_logger = MagicMock()
    monkeypatch.setattr("security.security_logger.security_logger_instance", mock_logger)
    log_security_event("VERBOSE", "test_event", {})
    mock_logger.info.assert_called_once()


# ── get_recent_events tests ───────────────────────────────────────────────────

def test_get_recent_events_no_file_returns_empty(monkeypatch, tmp_path):
    """get_recent_events returns [] when the log file doesn't exist."""
    monkeypatch.setattr("security.security_logger._SECURITY_LOG_PATH",
                        tmp_path / "nonexistent.log")
    result = get_recent_events(10)
    assert result == []


def test_get_recent_events_parses_valid_json(monkeypatch, tmp_path):
    """get_recent_events correctly parses JSON entries from the log."""
    log_file = tmp_path / "security.log"
    entry = {"timestamp": "2026-01-01T00:00:00", "severity": "INFO",
             "event_type": "test", "details": {}}
    # Write in the format security_logger produces: "timestamp [LEVEL] name — {json}"
    log_file.write_text(f'2026-01-01 INFO delkaai.security \u2014 {json.dumps(entry)}\n')

    monkeypatch.setattr("security.security_logger._SECURITY_LOG_PATH", log_file)
    result = get_recent_events(10)
    assert len(result) == 1
    assert result[0]["event_type"] == "test"


def test_get_recent_events_respects_n_limit(monkeypatch, tmp_path):
    """get_recent_events returns at most n events."""
    log_file = tmp_path / "security.log"
    lines = []
    for i in range(10):
        entry = {"timestamp": f"2026-01-01T00:00:0{i}", "event_type": f"evt{i}",
                 "severity": "INFO", "details": {}}
        lines.append(f'ts INFO name \u2014 {json.dumps(entry)}')
    log_file.write_text("\n".join(lines))

    monkeypatch.setattr("security.security_logger._SECURITY_LOG_PATH", log_file)
    result = get_recent_events(3)
    assert len(result) == 3


def test_get_recent_events_skips_malformed_lines(monkeypatch, tmp_path):
    """get_recent_events skips lines that are not valid JSON."""
    log_file = tmp_path / "security.log"
    valid_entry = {"timestamp": "2026-01-01T00:00:00", "event_type": "ok",
                   "severity": "INFO", "details": {}}
    log_file.write_text(
        f"not-a-json-line\n"
        f'ts INFO name \u2014 {json.dumps(valid_entry)}\n'
    )
    monkeypatch.setattr("security.security_logger._SECURITY_LOG_PATH", log_file)
    result = get_recent_events(10)
    # Only the valid line parsed
    assert len(result) == 1
    assert result[0]["event_type"] == "ok"


def test_get_recent_events_line_without_separator(monkeypatch, tmp_path):
    """Lines without the em-dash separator are treated as raw JSON."""
    log_file = tmp_path / "security.log"
    entry = {"event_type": "direct", "severity": "INFO", "details": {}}
    log_file.write_text(json.dumps(entry) + "\n")
    monkeypatch.setattr("security.security_logger._SECURITY_LOG_PATH", log_file)
    result = get_recent_events(10)
    assert len(result) == 1
    assert result[0]["event_type"] == "direct"
