from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


class DeveloperRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company: Optional[str] = None


class DeveloperLoginRequest(BaseModel):
    email: EmailStr
    password: str


class DeveloperAccountInfo(BaseModel):
    id: int
    email: str
    full_name: str
    company: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: Optional[datetime]


class DeveloperSessionInfo(BaseModel):
    session_token: str
    developer_id: int
    expires_at: datetime
    created_at: datetime
