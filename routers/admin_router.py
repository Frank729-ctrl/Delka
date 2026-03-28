import io
import json
import csv as csv_module
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from database import get_db
from schemas.admin_schema import CreateKeyPairRequest, RevokeKeyRequest, UnblockIPRequest
from services import admin_service
from services.metrics_service import get_summary
from security.ip_blocker import list_blocked, unblock_ip
from job_queue.job_queue import get_job_status

router = APIRouter(prefix="/v1/admin", tags=["admin"])


async def require_master_key(
    x_delkaai_master_key: str = Header(..., alias="X-DelkaAI-Master-Key"),
) -> None:
    if x_delkaai_master_key != settings.SECRET_MASTER_KEY:
        raise HTTPException(status_code=401, detail="Invalid master key.")


@router.get("/ping")
async def admin_ping():
    return {"admin_router": "ok"}


@router.post("/keys/create", status_code=201, dependencies=[Depends(require_master_key)])
async def create_keys(
    data: CreateKeyPairRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.create_key_pair(
        platform=data.platform,
        owner=data.owner,
        requires_hmac=data.requires_hmac,
        db=db,
    )
    return JSONResponse(
        status_code=201,
        content={"status": "success", "message": "Key pair created.", "data": result},
    )


@router.post("/keys/revoke", dependencies=[Depends(require_master_key)])
async def revoke_key(
    data: RevokeKeyRequest,
    db: AsyncSession = Depends(get_db),
):
    revoked = await admin_service.revoke_key(data.key_prefix, db)
    if not revoked:
        raise HTTPException(status_code=404, detail="Key prefix not found.")
    return {"status": "success", "message": "Key revoked.", "data": None}


@router.get("/keys/list", dependencies=[Depends(require_master_key)])
async def list_keys(db: AsyncSession = Depends(get_db)):
    keys = await admin_service.list_api_keys(db)
    return {
        "status": "success",
        "message": "success",
        "data": [k.model_dump() for k in keys],
    }


@router.get("/keys/{prefix}/usage", dependencies=[Depends(require_master_key)])
async def key_usage(prefix: str, db: AsyncSession = Depends(get_db)):
    usage = await admin_service.get_key_usage(prefix, db)
    if not usage:
        raise HTTPException(status_code=404, detail="Key prefix not found.")
    return {"status": "success", "message": "success", "data": usage}


@router.get("/metrics", dependencies=[Depends(require_master_key)])
async def metrics():
    summary = await get_summary()
    return {"status": "success", "message": "success", "data": summary}


@router.get("/blocked-ips", dependencies=[Depends(require_master_key)])
async def get_blocked_ips(db: AsyncSession = Depends(get_db)):
    blocked = await list_blocked(db)
    return {"status": "success", "message": "success", "data": blocked}


@router.post("/unblock-ip", dependencies=[Depends(require_master_key)])
async def unblock(data: UnblockIPRequest, db: AsyncSession = Depends(get_db)):
    removed = await unblock_ip(data.ip_address, db)
    if not removed:
        raise HTTPException(status_code=404, detail="IP address not found in blocklist.")
    return {"status": "success", "message": "IP unblocked.", "data": None}


@router.get("/jobs/{job_id}", dependencies=[Depends(require_master_key)])
async def job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    status = await get_job_status(job_id, db)
    return {"status": "success", "message": "success", "data": status}


@router.get("/ab-results", dependencies=[Depends(require_master_key)])
async def ab_results(
    task: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    from services.ab_test_service import get_ab_results
    results = await get_ab_results(task, db)
    return {"status": "success", "message": "success", "data": results}


@router.get("/training/stats", dependencies=[Depends(require_master_key)])
async def training_stats(
    platform: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from services.feedback_service import get_training_stats
    stats = await get_training_stats(db, platform=platform)
    return {"status": "success", "message": "success", "data": stats}


@router.get("/training/export", dependencies=[Depends(require_master_key)])
async def training_export(
    platform: str = Query(None),
    service: str = Query(None),
    min_rating: int = Query(4),
    format: str = Query("jsonl"),
    db: AsyncSession = Depends(get_db),
):
    from services.feedback_service import export_training_data
    rows = await export_training_data(db, platform=platform, service=service, min_rating=min_rating)

    if format == "csv":
        output = io.StringIO()
        if rows:
            writer = csv_module.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        filename = f"delkaai_training_data_{service or 'all'}_{platform or 'all'}.csv"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # Default: JSONL
    jsonl = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    filename = f"delkaai_training_data_{service or 'all'}_{platform or 'all'}.jsonl"
    return StreamingResponse(
        io.BytesIO(jsonl.encode("utf-8")),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
