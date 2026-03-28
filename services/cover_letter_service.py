import uuid
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.cover_letter_schema import CoverLetterRequest
from services.language_service import detect_language, get_language_instruction
from services.template_service import pick_random_letter_template
from services.export_service import render_letter_to_pdf
from services.inference_service import generate_full_response as _inference_full
from services.output_validator import clean_letter_output
from prompts.cover_letter_prompt import build_letter_prompt
from services.quality_scorer import score_letter_output, log_quality_result
from job_queue.job_queue import enqueue_job


async def _run_letter_pipeline(payload: dict) -> tuple[bytes, str, str, str, str, dict]:
    data = CoverLetterRequest(**payload)
    lang = detect_language(data.applicant_background)
    lang_instruction = get_language_instruction(lang)
    sys_prompt, user_prompt = build_letter_prompt(data, lang_instruction)
    raw, provider, model = await _inference_full("letter", sys_prompt, user_prompt)
    letter_text = clean_letter_output(raw)

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
    return pdf_bytes, template_name, template_name, provider, model, quality


async def generate_cover_letter(
    data: CoverLetterRequest,
    db: AsyncSession,
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

    return await _run_letter_pipeline(data.model_dump())
