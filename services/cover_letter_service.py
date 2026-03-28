import hashlib
import time
import uuid
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.cover_letter_schema import CoverLetterRequest
from services.language_service import detect_language, get_language_instruction
from services.template_service import pick_random_letter_template
from services.export_service import render_letter_to_pdf
from services.inference_service import generate_full_response as _inference_full
from services.output_validator import clean_letter_output, strip_thinking_blocks
from prompts.cover_letter_prompt import build_letter_prompt
from services.quality_scorer import score_letter_output, log_quality_result
from job_queue.job_queue import enqueue_job


async def _run_letter_pipeline(
    payload: dict,
    db: AsyncSession | None = None,
    user_id: str = "anon",
    platform: str = "unknown",
) -> tuple[bytes, str, str, str, str, dict]:
    start_ms = int(time.time() * 1000)
    data = CoverLetterRequest(**payload)
    lang = detect_language(data.applicant_background)
    lang_instruction = get_language_instruction(lang)
    sys_prompt, user_prompt = build_letter_prompt(data, lang_instruction)
    raw, provider, model = await _inference_full("letter", sys_prompt, user_prompt, user_id=user_id)

    # Extract thinking blocks before cleaning
    _, thinking_blocks = strip_thinking_blocks(raw)

    letter_text = clean_letter_output(raw)
    response_ms = int(time.time() * 1000) - start_ms

    quality = score_letter_output(letter_text)
    log_quality_result("cover_letter", quality)

    meta = {
        "applicant_name": data.applicant_name,
        "company_name": data.company_name,
        "job_title": data.job_title,
        "date": date.today().strftime("%B %d, %Y"),
    }

    template_name, color = pick_random_letter_template()
    pdf_bytes = render_letter_to_pdf(letter_text, meta, template_name, color)

    if db is not None:
        try:
            from services.feedback_service import store_feedback_log
            await store_feedback_log(
                user_id=user_id,
                platform=platform,
                session_id=str(uuid.uuid4()),
                service="letter",
                request_data=payload,
                response_data={"letter_text": letter_text},
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
            pass

    return pdf_bytes, template_name, template_name, provider, model, quality


async def generate_cover_letter(
    data: CoverLetterRequest,
    db: AsyncSession,
    user_id: str = "anon",
    platform: str = "unknown",
) -> tuple[bytes, str, str, str, str, dict] | dict:
    if data.webhook_url:
        job_id = str(uuid.uuid4())
        await enqueue_job(
            job_id=job_id,
            job_type="cover_letter",
            payload=data.model_dump(),
            webhook_url=data.webhook_url,
            key_prefix=None,
            db=db,
        )
        return {"job_id": job_id, "status": "queued"}

    return await _run_letter_pipeline(data.model_dump(), db, user_id, platform)
