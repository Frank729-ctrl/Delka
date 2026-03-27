from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SettingItem(BaseModel):
    setting_key: str
    setting_value: str
    description: Optional[str] = None
    updated_at: datetime
    updated_by: Optional[str] = None


class UpsertSettingRequest(BaseModel):
    setting_key: str
    setting_value: str
    description: Optional[str] = None
