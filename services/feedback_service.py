from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.feedback_schema import FeedbackRequest, FeedbackResponse, FeedbackSummary


def is_training_eligible(log) -> bool:
    """Return True only if this interaction is high quality and suitable for fine-tuning."""
    if log.rating is None or log.rating < 4:
        return False
    if log.correction:
        return False
    response_text = str(log.response_data)
    if len(response_text) < 200:
        return False
    if log.auto_score is not None and log.auto_score < 0.65:
        return False
    return True


async def store_feedback_log(
    user_id: str,
    platform: str,
    session_id: str,
    service: str,
    request_data: dict,
    response_data: dict,
    provider_used: str,
    model_used: str,
    response_ms: int,
    db: AsyncSession,
    auto_score: float | None = None,
    auto_score_issues: list | None = None,
    system_prompt_hash: str | None = None,
    thinking_tokens: str | None = None,
) -> None:
    from models.feedback_log_model import FeedbackLog

    entry = FeedbackLog(
        user_id=user_id,
        platform=platform,
        session_id=session_id,
        service=service,
        request_data=request_data,
        system_prompt_hash=system_prompt_hash,
        response_data=response_data,
        thinking_tokens=thinking_tokens,
        provider_used=provider_used,
        model_used=model_used,
        response_ms=response_ms,
        auto_score=auto_score,
        auto_score_issues=auto_score_issues or [],
    )
    db.add(entry)


async def store_feedback(
    data: FeedbackRequest,
    user_id: str,
    platform: str,
    db: AsyncSession,
) -> dict:
    from models.feedback_log_model import FeedbackLog
    from services.memory_service import add_correction_rule, get_or_create_profile

    # Find existing log or create placeholder
    result = await db.execute(
        select(FeedbackLog).where(
            FeedbackLog.session_id == data.session_id,
            FeedbackLog.service == data.service,
        )
    )
    log = result.scalar_one_or_none()
    if log is None:
        log = FeedbackLog(
            user_id=user_id,
            platform=platform,
            session_id=data.session_id,
            service=data.service,
            request_data={},
            response_data={},
            response_ms=0,
        )
        db.add(log)
        await db.flush()

    log.rating = data.rating
    if data.comment:
        log.rating_comment = data.comment
    if data.correction:
        log.correction = data.correction

    correction_stored = False
    if data.correction:
        await add_correction_rule(user_id, platform, data.correction, db)
        correction_stored = True

    # Update user's avg rating
    await _update_avg_rating(user_id, platform, db)

    return {"stored": True, "correction_stored": correction_stored}


async def _update_avg_rating(user_id: str, platform: str, db: AsyncSession) -> None:
    from models.feedback_log_model import FeedbackLog
    from models.user_memory_profile_model import UserMemoryProfile
    from sqlalchemy import select

    result = await db.execute(
        select(func.avg(FeedbackLog.rating)).where(
            FeedbackLog.user_id == user_id,
            FeedbackLog.rating.isnot(None),
        )
    )
    avg = result.scalar_one_or_none() or 0.0

    profile_result = await db.execute(
        select(UserMemoryProfile).where(
            UserMemoryProfile.user_id == user_id,
            UserMemoryProfile.platform == platform,
        )
    )
    profile = profile_result.scalar_one_or_none()
    if profile:
        profile.avg_rating_given = float(avg)


async def get_rag_examples(
    user_id: str,
    platform: str,
    service: str,
    db: AsyncSession,
    limit: int = 3,
) -> list[dict]:
    from models.feedback_log_model import FeedbackLog

    result = await db.execute(
        select(FeedbackLog)
        .where(
            FeedbackLog.user_id == user_id,
            FeedbackLog.platform == platform,
            FeedbackLog.service == service,
            FeedbackLog.rating >= 4,
        )
        .order_by(FeedbackLog.rating.desc(), FeedbackLog.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {"request_data": r.request_data, "response_data": r.response_data}
        for r in rows
    ]


async def get_feedback_summary(
    platform: str,
    db: AsyncSession,
    service: str = None,
) -> list[FeedbackSummary]:
    from models.feedback_log_model import FeedbackLog

    query = select(
        FeedbackLog.service,
        func.avg(FeedbackLog.rating).label("avg_rating"),
        func.count(FeedbackLog.rating).label("total_ratings"),
        func.count(FeedbackLog.correction).label("total_corrections"),
    ).where(
        FeedbackLog.platform == platform,
        FeedbackLog.rating.isnot(None),
    )
    if service:
        query = query.where(FeedbackLog.service == service)
    query = query.group_by(FeedbackLog.service)

    result = await db.execute(query)
    rows = result.all()
    return [
        FeedbackSummary(
            service=r.service,
            avg_rating=round(float(r.avg_rating or 0), 2),
            total_ratings=r.total_ratings or 0,
            total_corrections=r.total_corrections or 0,
        )
        for r in rows
    ]


def _build_prompt_text(log) -> str:
    """Reconstruct a human-readable prompt string from stored request_data."""
    import json
    svc = log.service or ""
    if svc == "cv":
        return f"Generate a professional CV:\n{json.dumps(log.request_data, ensure_ascii=False)}"
    if svc == "letter":
        return f"Write a cover letter:\n{json.dumps(log.request_data, ensure_ascii=False)}"
    if svc in ("chat", "support"):
        return log.request_data.get("message", json.dumps(log.request_data))
    return json.dumps(log.request_data, ensure_ascii=False)


def _build_completion_text(log) -> str:
    """Reconstruct the completion string from stored response_data."""
    import json
    svc = log.service or ""
    if svc == "cv":
        return json.dumps(log.response_data, ensure_ascii=False)
    if svc in ("letter", "chat", "support"):
        return log.response_data.get("response") or log.response_data.get("letter_text") or json.dumps(log.response_data, ensure_ascii=False)
    return json.dumps(log.response_data, ensure_ascii=False)


async def export_training_data(
    db: AsyncSession,
    platform: str | None = None,
    service: str | None = None,
    min_rating: int = 4,
) -> list[dict]:
    from models.feedback_log_model import FeedbackLog

    query = select(FeedbackLog)
    if platform:
        query = query.where(FeedbackLog.platform == platform)
    if service:
        query = query.where(FeedbackLog.service == service)
    query = query.order_by(FeedbackLog.created_at.desc())

    result = await db.execute(query)
    rows = result.scalars().all()

    out = []
    for r in rows:
        if not is_training_eligible(r):
            continue
        out.append({
            "prompt": _build_prompt_text(r),
            "completion": _build_completion_text(r),
            "rating": r.rating,
            "platform": r.platform,
            "service": r.service,
            "model": r.model_used or "",
            "auto_score": r.auto_score,
        })
    return out


async def get_training_stats(
    db: AsyncSession,
    platform: str | None = None,
) -> dict:
    from models.feedback_log_model import FeedbackLog
    from sqlalchemy import and_, or_

    query = select(FeedbackLog)
    if platform:
        query = query.where(FeedbackLog.platform == platform)

    result = await db.execute(query)
    rows = result.scalars().all()

    services = ["cv", "letter", "chat", "support", "vision"]
    by_service: dict = {s: {"total": 0, "rated": 0, "high_quality": 0} for s in services}
    total = rated = high_quality = 0
    score_sum = score_count = rating_sum = rating_count = 0

    for r in rows:
        svc = r.service or "other"
        bucket = by_service.setdefault(svc, {"total": 0, "rated": 0, "high_quality": 0})

        total += 1
        bucket["total"] += 1

        if r.rating is not None:
            rated += 1
            bucket["rated"] += 1
            rating_sum += r.rating
            rating_count += 1

        if is_training_eligible(r):
            high_quality += 1
            bucket["high_quality"] += 1

        if r.auto_score is not None:
            score_sum += r.auto_score
            score_count += 1

    _THRESHOLD = 300
    ready = high_quality >= _THRESHOLD

    if not ready and rated > 0:
        rate_per_day = rated / max(1, (rows[-1].created_at - rows[0].created_at).days or 1) if len(rows) > 1 else 1
        weeks_needed = max(0, (_THRESHOLD - high_quality) / max(1, rate_per_day * 7))
        readiness = f"~{int(weeks_needed)} weeks at current rate"
    elif ready:
        readiness = "ready"
    else:
        readiness = "not enough data yet"

    return {
        "total_interactions": total,
        "rated_interactions": rated,
        "high_quality": high_quality,
        "by_service": {k: v for k, v in by_service.items() if v["total"] > 0},
        "fine_tuning_ready": ready,
        "fine_tuning_threshold": _THRESHOLD,
        "estimated_readiness": readiness,
        "avg_auto_score": round(score_sum / score_count, 3) if score_count else None,
        "avg_user_rating": round(rating_sum / rating_count, 2) if rating_count else None,
    }
