"""Unit tests for services/developer_auth_service.py."""
import pytest
from services.developer_auth_service import (
    register_developer,
    login_developer,
    get_session,
    logout_developer,
)


async def test_register_creates_account(test_db):
    """register_developer returns success and a developer_id."""
    result = await register_developer("alice@example.com", "password123", "Alice", None, test_db)
    assert result["success"] is True
    assert "developer_id" in result
    assert isinstance(result["developer_id"], int)


async def test_register_duplicate_email_fails(test_db):
    """Registering the same email twice returns email_taken error."""
    await register_developer("bob@example.com", "pass1", "Bob", None, test_db)
    result = await register_developer("bob@example.com", "pass2", "Bob Again", None, test_db)
    assert result["success"] is False
    assert result["error"] == "email_taken"


async def test_register_normalises_email_to_lowercase(test_db):
    """Email is stored lowercase; duplicate check is case-insensitive."""
    await register_developer("Carol@Example.COM", "pass", "Carol", None, test_db)
    result = await register_developer("carol@example.com", "pass2", "Carol2", None, test_db)
    assert result["success"] is False
    assert result["error"] == "email_taken"


async def test_login_valid_credentials_returns_token(test_db):
    """Login with valid credentials returns a session token."""
    await register_developer("dave@example.com", "securepass", "Dave", "Acme", test_db)
    result = await login_developer("dave@example.com", "securepass", "127.0.0.1", "test-ua", test_db)
    assert result["success"] is True
    assert "session_token" in result
    assert len(result["session_token"]) == 128  # 64-byte hex


async def test_login_wrong_password_fails(test_db):
    """Login with wrong password returns invalid_credentials."""
    await register_developer("eve@example.com", "correct", "Eve", None, test_db)
    result = await login_developer("eve@example.com", "wrong", None, None, test_db)
    assert result["success"] is False
    assert result["error"] == "invalid_credentials"


async def test_login_unknown_email_fails(test_db):
    """Login with unknown email returns invalid_credentials."""
    result = await login_developer("nobody@example.com", "any", None, None, test_db)
    assert result["success"] is False
    assert result["error"] == "invalid_credentials"


async def test_get_session_returns_account_for_valid_token(test_db):
    """get_session returns the DeveloperAccount for a valid token."""
    await register_developer("frank@example.com", "pass", "Frank", None, test_db)
    login = await login_developer("frank@example.com", "pass", None, None, test_db)
    token = login["session_token"]
    account = await get_session(token, test_db)
    assert account is not None
    assert account.email == "frank@example.com"


async def test_get_session_returns_none_for_invalid_token(test_db):
    """get_session returns None for a non-existent token."""
    account = await get_session("invalidtoken" * 8, test_db)
    assert account is None


async def test_get_session_returns_none_for_empty_token(test_db):
    """get_session with None/empty token returns None."""
    assert await get_session(None, test_db) is None
    assert await get_session("", test_db) is None


async def test_logout_invalidates_session(test_db):
    """Logging out makes the session token invalid."""
    await register_developer("grace@example.com", "pass", "Grace", None, test_db)
    login = await login_developer("grace@example.com", "pass", None, None, test_db)
    token = login["session_token"]

    ok = await logout_developer(token, test_db)
    assert ok is True

    account = await get_session(token, test_db)
    assert account is None


async def test_logout_nonexistent_token_returns_false(test_db):
    """Logging out with an unknown token returns False."""
    result = await logout_developer("nonexistenttoken" * 8, test_db)
    assert result is False
