from security.key_hasher import hash_key, verify_key


def test_hash_returns_string():
    result = hash_key("fd-delka-sk-abc123")
    assert isinstance(result, str)
    assert len(result) > 0


def test_verify_correct_key_returns_true():
    raw = "fd-delka-sk-testkey00000000000000"
    stored = hash_key(raw)
    assert verify_key(raw, stored) is True


def test_verify_wrong_key_returns_false():
    raw = "fd-delka-sk-testkey00000000000000"
    stored = hash_key(raw)
    assert verify_key("fd-delka-sk-wrongkey0000000000000", stored) is False


def test_different_inputs_produce_different_hashes():
    h1 = hash_key("key-one")
    h2 = hash_key("key-two")
    assert h1 != h2


def test_verify_does_not_raise_on_garbage_hash():
    result = verify_key("any-key", "not-a-valid-argon2-hash")
    assert result is False
