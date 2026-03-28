import hashlib
import time
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.cv_schema import CVRequest
from services.language_service import detect_language, get_language_instruction
from services.template_service import pick_random_cv_template
from services.export_service import render_cv_to_pdf
from services.inference_service import generate_full_response as _inference_full
from services.output_validator import validate_and_parse_cv, strip_thinking_blocks
from prompts.cv_prompt import build_cv_prompt
from services.quality_scorer import score_cv_output, log_quality_result
from job_queue.job_queue import enqueue_job


class _CVRetryAdapter:
    """Wraps inference_service for use by output_validator retry logic."""
    async def generate_full_response(self, sys_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        text, _, _ = await _inference_full("cv", sys_prompt, user_prompt, temperature)
        return text


_cv_retry = _CVRetryAdapter()


async def _run_cv_pipeline(
    payload: dict,
    db: AsyncSession | None = None,
    user_id: str = "anon",
    platform: str = "unknown",
) -> tuple[bytes, str, str, str, str, dict]:
    start_ms = int(time.time() * 1000)
    data = CVRequest(**payload)
    lang = detect_language(data.summary)
    lang_instruction = get_language_instruction(lang)
    sys_prompt, user_prompt = build_cv_prompt(data, lang_instruction)
    raw, provider, model = await _inference_full("cv", sys_prompt, user_prompt, user_id=user_id)

    # Extract thinking blocks before validation
    _, thinking_blocks = strip_thinking_blocks(raw)

    cv_data = await validate_and_parse_cv(raw, _cv_retry, sys_prompt, user_prompt)
    response_ms = int(time.time() * 1000) - start_ms

    quality = score_cv_output(cv_data)
    log_quality_result("cv", quality)

    template_name, color = pick_random_cv_template()
    pdf_bytes = render_cv_to_pdf(cv_data, template_name, color)

    if db is not None:
        try:
            from services.feedback_service import store_feedback_log
            await store_feedback_log(
                user_id=user_id,
                platform=platform,
                session_id=str(uuid.uuid4()),
                service="cv",
                request_data=payload,
                response_data=cv_data,
                provider_used=provider,
                model_used=model,
                response_ms=response_ms,
                db=db,
                auto_score=quality["total_score"],
                auto_score_issues=quality.get("issues", []),
                system_prompt_hash=hashlib.sha256(sys_prompt.encode()).hexdigest(),
                thinking_tokens="\n".join(thinking_blocks) if thinking_blocks else None,
            )
            await db.commit()
        except Exception:
            pass  # logging failures never break generation

    return pdf_bytes, template_name, template_name, provider, model, quality


async def generate_cv(
    data: CVRequest,
    db: AsyncSession,
    user_id: str = "anon",
    platform: str = "unknown",
) -> tuple[bytes, str, str, str, str, dict] | dict:
    if data.webhook_url:
        job_id = str(uuid.uuid4())
        await enqueue_job(
            job_id=job_id,
            job_type="cv",
            payload=data.model_dump(),
            webhook_url=data.webhook_url,
            key_prefix=None,
            db=db,
        )
        return {"job_id": job_id, "status": "queued"}

    return await _run_cv_pipeline(data.model_dump(), db, user_id, platform)
