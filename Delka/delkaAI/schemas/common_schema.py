from typing import Any, Literal
from pydantic import BaseModel


class StandardResponse(BaseModel):
    status: Literal["success", "error"]
    message: str
    data: Any = None


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    message: str
    data: Any = None
