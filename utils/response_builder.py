from typing import Any, Optional


def build_success(data: Any = None, message: str = "success") -> dict:
    return {
        "status": "success",
        "message": message,
        "data": data,
    }


def build_error(message: str = "error", request_id: Optional[str] = None) -> dict:
    return {
        "status": "error",
        "message": message,
        "data": {"request_id": request_id} if request_id else None,
    }
