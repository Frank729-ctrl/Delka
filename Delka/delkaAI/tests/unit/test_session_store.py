"""Tests for sessions/chat_session_store.py — all functions and edge cases."""
import pytest
import sessions.chat_session_store as store


@pytest.fixture(autouse=True)
def clear_sessions():
    """Clear session state before each test to avoid bleed-through."""
    store._sessions.clear()
    yield
    store._sessions.clear()


def test_new_session_history_is_empty():
    """get_history on a new session_id returns empty list."""
    assert store.get_history("new-session-id") == []


def test_append_message_adds_to_history():
    """append_message correctly adds a message to the session."""
    store.append_message("s1", "user", "Hello")
    history = store.get_history("s1")
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"


def test_history_preserves_order():
    """Multiple messages are returned in insertion order."""
    store.append_message("s2", "user", "first")
    store.append_message("s2", "assistant", "second")
    store.append_message("s2", "user", "third")
    history = store.get_history("s2")
    assert history[0]["content"] == "first"
    assert history[1]["content"] == "second"
    assert history[2]["content"] == "third"


def test_clear_session_removes_history():
    """clear_session removes all messages from the session."""
    store.append_message("s3", "user", "hello")
    store.clear_session("s3")
    assert store.get_history("s3") == []


def test_clear_nonexistent_session_does_not_raise():
    """clear_session on an unknown session_id silently succeeds."""
    store.clear_session("does-not-exist")  # Should not raise


def test_get_session_length_counts_messages():
    """get_session_length returns the correct count."""
    store.append_message("s4", "user", "msg1")
    store.append_message("s4", "assistant", "msg2")
    assert store.get_session_length("s4") == 2


def test_get_session_length_empty_session():
    """get_session_length on unknown session returns 0."""
    assert store.get_session_length("unknown-session") == 0


def test_sessions_are_independent():
    """Messages in one session do not appear in another."""
    store.append_message("alpha", "user", "hello alpha")
    store.append_message("beta", "user", "hello beta")
    assert len(store.get_history("alpha")) == 1
    assert store.get_history("alpha")[0]["content"] == "hello alpha"
    assert store.get_history("beta")[0]["content"] == "hello beta"


def test_history_is_capped_at_max_history():
    """Appending more than _MAX_HISTORY messages keeps only the last 20."""
    for i in range(25):
        store.append_message("s5", "user", f"msg{i}")
    history = store.get_history("s5")
    assert len(history) == store._MAX_HISTORY
    # Last message should be the most recent one
    assert history[-1]["content"] == "msg24"


def test_get_history_returns_copy():
    """get_history returns a copy — mutating it doesn't affect stored history."""
    store.append_message("s6", "user", "original")
    history = store.get_history("s6")
    history.append({"role": "user", "content": "injected"})
    assert len(store.get_history("s6")) == 1
