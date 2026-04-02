from fastapi import APIRouter, HTTPException
from schemas.translation_schema import TranslationRequest, TranslationResponse
from services.translation_service import translate

router = APIRouter(prefix="/v1/translate")


@router.post("/", response_model=TranslationResponse)
async def translation_translate(request: TranslationRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="text is required.")

    translated, source_lang, provider = await translate(
        text=request.text,
        source_lang=request.source_lang,
        target_lang=request.target_lang,
    )
    if provider == "unavailable":
        raise HTTPException(status_code=503, detail="Translation service unavailable.")

    return TranslationResponse(
        translated_text=translated,
        source_lang=source_lang,
        target_lang=request.target_lang,
        provider=provider,
    )
