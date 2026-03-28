import asyncio
import base64
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.webhook_model import WebhookJob
from utils.logger import request_logger

_queue: asyncio.Queue = asyncio.Queue()


async def enqueue_job(
    job_id: str,
    job_type: str,
    payload: dict,
    webhook_url: str,
    key_prefix: str | None,
    db: AsyncSession,
) -> None:
    record = WebhookJob(
        job_id=job_id,
        job_type=job_type,
        status="queued",
        webhook_url=webhook_url,
        payload=payload,
        key_prefix=key_prefix,
    )
    db.add(record)
    await db.commit()
    await _queue.put(job_id)


async def get_job_status(job_id: str, db: AsyncSession) -> dict:
    result = await db.execute(
        select(WebhookJob).where(WebhookJob.job_id == job_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return {"job_id": job_id, "status": "not_found"}
    return {
        "job_id": record.job_id,
        "job_type": record.job_type,
        "status": record.status,
        "attempts": record.attempts,
        "created_at": record.created_at.isoformat(),
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }


async def _process_one(job_id: str, db: AsyncSession) -> None:
    from services.cv_service import _run_cv_pipeline
    from services.cover_letter_service import _run_letter_pipeline
    from services import webhook_service
    from config import settings

    result = await db.execute(
        select(WebhookJob).where(WebhookJob.job_id == job_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return

    record.status = "processing"
    record.attempts += 1
    await db.commit()

    try:
        pdf_bytes: bytes

        if record.job_type == "cv":
            pdf_bytes, template_name, color_key, _provider, _model, _quality = await _run_cv_pipeline(record.payload, db)
        elif record.job_type == "cover_letter":
            pdf_bytes, template_name, color_key, _provider, _model, _quality = await _run_letter_pipeline(record.payload, db)
        else:
            raise ValueError(f"Unknown job_type: {record.job_type}")

        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
        record.result = {
            "pdf_base64": pdf_b64,
            "template": template_name,
            "color": color_key,
        }
        record.status = "complete"
        record.completed_at = datetime.utcnow()
        await db.commit()

        webhook_payload = {
            "job_id": job_id,
            "status": "complete",
            "event": f"{record.job_type}.generated",
            "data": record.result,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await webhook_service.deliver(
            url=record.webhook_url,
            payload=webhook_payload,
            secret=settings.SECRET_MASTER_KEY,
        )

    except Exception as exc:
        request_logger.error(f"job_queue: job_id={job_id} failed error={exc}")
        record.status = "failed"
        record.completed_at = datetime.utcnow()
        await db.commit()


async def process_jobs(db_factory) -> None:
    request_logger.info("job_queue: processor started")
    while True:
        try:
            job_id = await _queue.get()
            async with db_factory() as db:
                await _process_one(job_id, db)
            _queue.task_done()
        except asyncio.CancelledError:
            request_logger.info("job_queue: processor shutting down")
            break
        except Exception as exc:
            request_logger.error(f"job_queue: unhandled error error={exc}")
