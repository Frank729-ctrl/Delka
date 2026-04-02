"""
Analytics & metrics admin router.

GET  /v1/admin/analytics/metrics   — hourly aggregated metrics
GET  /v1/admin/analytics/flags     — list feature flags
POST /v1/admin/analytics/flags     — set a feature flag
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any

from services.analytics_service import get_metrics_snapshot, get_feature_flag, set_feature_flag

router = APIRouter(prefix="/v1/admin/analytics")


@router.get("/metrics")
async def api_metrics():
    return {"status": "ok", "data": get_metrics_snapshot()}


class FlagRequest(BaseModel):
    flag: str
    value: Any


@router.get("/flags/{flag}")
async def api_get_flag(flag: str):
    return {"flag": flag, "value": get_feature_flag(flag)}


@router.post("/flags")
async def api_set_flag(req: FlagRequest):
    set_feature_flag(req.flag, req.value)
    return {"status": "ok", "flag": req.flag, "value": req.value}
