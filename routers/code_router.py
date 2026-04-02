from fastapi import APIRouter, HTTPException
from schemas.code_schema import CodeRequest, CodeResponse
from services.code_service import generate_code

router = APIRouter(prefix="/v1/code")


@router.post("/generate", response_model=CodeResponse)
async def code_generate(request: CodeRequest):
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required.")

    code, language, explanation, provider, model = await generate_code(
        prompt=request.prompt,
        language=request.language,
        context=request.context,
        max_tokens=request.max_tokens,
        user_id=request.user_id,
    )
    if provider == "none":
        raise HTTPException(status_code=503, detail="Code generation unavailable.")

    return CodeResponse(
        code=code,
        language=language,
        explanation=explanation,
        provider=provider,
        model=model,
    )
