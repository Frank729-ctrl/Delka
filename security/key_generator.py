import secrets


def generate_key_pair() -> dict:
    pk = f"fd-delka-pk-{secrets.token_hex(16)}"
    sk = f"fd-delka-sk-{secrets.token_hex(16)}"
    hmac_secret = f"fd-delka-hm-{secrets.token_hex(24)}"
    return {
        "publishable_key": pk,
        "secret_key": sk,
        "hmac_secret": hmac_secret,
    }


def generate_master_key() -> str:
    return f"fd-delka-mk-{secrets.token_hex(16)}"
