from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.feedback_schema import FeedbackRequest, FeedbackResponse, FeedbackSummary


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
) -> None:
    from models.feedback_log_model import FeedbackLog

    entry = FeedbackLog(
        user_id=user_id,
        platform=platform,
        session_id=session_id,
        service=service,
        request_data=request_data,
        response_data=response_data,
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


async def export_training_data(
    platform: str,
    db: AsyncSession,
    min_rating: int = 4,
) -> list[dict]:
    from models.feedback_log_model import FeedbackLog

    result = await db.execute(
        select(FeedbackLog).where(
            FeedbackLog.platform == platform,
            FeedbackLog.rating >= min_rating,
        )
    )
    rows = result.scalars().all()
    return [
        {
            "prompt": str(r.request_data),
            "completion": str(r.response_data),
            "rating": r.rating,
            "platform": r.platform,
        }
        for r in rows
    ]
