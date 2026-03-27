import re
from security.key_generator import generate_key_pair, generate_master_key

_PK_RE = re.compile(r"^fd-delka-pk-[0-9a-f]{32}$")
_SK_RE = re.compile(r"^fd-delka-sk-[0-9a-f]{32}$")
_HM_RE = re.compile(r"^fd-delka-hm-[0-9a-f]{48}$")
_MK_RE = re.compile(r"^fd-delka-mk-[0-9a-f]{32}$")


def test_publishable_key_format():
    pair = generate_key_pair()
    assert _PK_RE.match(pair["publishable_key"]), f"Bad pk format: {pair['publishable_key']}"


def test_secret_key_format():
    pair = generate_key_pair()
    assert _SK_RE.match(pair["secret_key"]), f"Bad sk format: {pair['secret_key']}"


def test_hmac_secret_format():
    pair = generate_key_pair()
    assert _HM_RE.match(pair["hmac_secret"]), f"Bad hmac format: {pair['hmac_secret']}"


def test_keys_are_unique_across_calls():
    a = generate_key_pair()
    b = generate_key_pair()
    assert a["publishable_key"] != b["publishable_key"]
    assert a["secret_key"] != b["secret_key"]
    assert a["hmac_secret"] != b["hmac_secret"]


def test_master_key_format():
    mk = generate_master_key()
    assert _MK_RE.match(mk), f"Bad master key format: {mk}"
