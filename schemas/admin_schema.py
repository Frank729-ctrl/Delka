from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class CreateKeyPairRequest(BaseModel):
    platform: str
    owner: str
    requires_hmac: bool = False


class RevokeKeyRequest(BaseModel):
    key_prefix: str


class UnblockIPRequest(BaseModel):
    ip_address: str


class KeyInfo(BaseModel):
    raw_prefix: str
    key_type: str
    platform: str
    owner: str
    is_active: bool
    is_flagged: bool
    violation_count: int
    usage_count: int
    created_at: datetime
    last_used_at: Optional[datetime] = None
