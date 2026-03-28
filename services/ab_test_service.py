"""
A/B Testing Framework for DelkaAI.

Splits inference traffic between two models for a given task.
Same user always gets the same model (deterministic via hash).
Results endpoint computes winner once both groups have enough samples.
"""

import hashlib
from utils.logger import request_logger


def get_ab_config() -> dict | None:
    """Read A/B test config from settings. Returns None if test is disabled."""
    from config import settings
    if not settings.AB_TEST_ENABLED:
        return None

    return {
        "service": settings.AB_TEST_SERVICE,
        "model_a": {
            "provider": settings.AB_TEST_MODEL_A_PROVIDER,
            "model": settings.AB_TEST_MODEL_A_MODEL,
            "weight": settings.AB_TEST_MODEL_A_WEIGHT,
            "name": f"{settings.AB_TEST_MODEL_A_PROVIDER}/{settings.AB_TEST_MODEL_A_MODEL}",
        },
        "model_b": {
            "provider": settings.AB_TEST_MODEL_B_PROVIDER,
            "model": settings.AB_TEST_MODEL_B_MODEL,
            "weight": settings.AB_TEST_MODEL_B_WEIGHT,
            "name": f"{settings.AB_TEST_MODEL_B_PROVIDER}/{settings.AB_TEST_MODEL_B_MODEL}",
        },
        "min_samples": 200,
    }


def get_model_for_user(task: str, user_id: str) -> tuple[str, str] | None:
    """
    Assign user to Group A or B based on hash of user_id.
    Same user always lands in the same group — consistent experience.
    Returns (provider, model_name) or None if no active test for this task.
    """
    if not user_id:
        return None

    config = get_ab_config()
    if not config or config["service"] != task:
        return None

    # Deterministic: hash(user_id) mod 100, compare to weight threshold
    user_hash = int(hashlib.md5(user_id.encode()).hexdigest(), 16) % 100
    threshold = int(config["model_a"]["weight"] * 100)

    m = config["model_a"] if user_hash < threshold else config["model_b"]

    request_logger.info(
        f"[AB] user={user_id[:8]}... task={task} hash={user_hash} → {m['name']}"
    )
    return m["provider"], m["model"]


async def get_ab_results(task: str, db) -> dict:
    """
    Aggregate ratings by model for the A/B test.
    Returns statistical summary with winner recommendation.
    """
    from models.feedback_log_model import FeedbackLog
    from sqlalchemy import select, func

    config = get_ab_config()
    if not config:
        return {"status": "no_test_active"}

    model_a_name = config["model_a"]["name"]
    model_b_name = config["model_b"]["name"]

    async def _get_stats(model_name: str) -> dict:
        # model_used column stores just the model slug (no provider prefix)
        model_slug = model_name.split("/")[-1]
        result = await db.execute(
            select(
                func.count(FeedbackLog.id).label("count"),
                func.avg(FeedbackLog.rating).label("avg_rating"),
            ).where(
                FeedbackLog.service == task,
                FeedbackLog.model_used == model_slug,
                FeedbackLog.rating.isnot(None),
            )
        )
        row = result.first()
        return {
            "name": model_name,
            "samples": row.count or 0,
            "avg_rating": round(float(row.avg_rating or 0), 3),
        }

    stats_a = await _get_stats(model_a_name)
    stats_b = await _get_stats(model_b_name)

    min_samples = config["min_samples"]
    winner = "inconclusive"
    confidence = 0.0
    recommendation = f"Continue testing — need {min_samples} samples per group"

    if stats_a["samples"] >= min_samples and stats_b["samples"] >= min_samples:
        diff = abs(stats_a["avg_rating"] - stats_b["avg_rating"])
        if diff >= 0.3:
            confidence = round(min(0.99, 0.7 + diff * 0.5), 3)
            if stats_a["avg_rating"] > stats_b["avg_rating"]:
                winner = "model_a"
                recommendation = f"Keep {model_a_name} as primary"
            else:
                winner = "model_b"
                recommendation = f"Promote {model_b_name} to primary"
        elif diff >= 0.1:
            confidence = 0.6
            winner = "model_b" if stats_b["avg_rating"] > stats_a["avg_rating"] else "model_a"
            recommendation = "Difference too small — collect more samples"
        else:
            recommendation = "Models are statistically equivalent"

    return {
        "task": task,
        "model_a": stats_a,
        "model_b": stats_b,
        "winner": winner,
        "confidence": confidence,
        "recommendation": recommendation,
        "min_samples_required": min_samples,
    }
