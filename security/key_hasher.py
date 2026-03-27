from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from config import settings

_hasher = PasswordHasher(
    time_cost=settings.ARGON2_TIME_COST,
    memory_cost=settings.ARGON2_MEMORY_COST,
    parallelism=settings.ARGON2_PARALLELISM,
)


def hash_key(raw: str) -> str:
    return _hasher.hash(raw)


def verify_key(raw: str, stored_hash: str) -> bool:
    try:
        return _hasher.verify(stored_hash, raw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception:
        return False
