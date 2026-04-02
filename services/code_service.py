"""
Code generation service.
Chain: Cerebras Qwen3-235B → Groq llama-3.3-70b → Ollama codellama
"""
import re
from config import settings
from services.inference_service import generate_full_response


_SYSTEM_PROMPT = """\
You are an expert programmer. Write clean, well-commented, production-ready code.
When writing code:
- Return the code in a proper markdown code block with language tag
- After the code block, add a brief explanation
- Handle edge cases and errors appropriately
- Follow best practices for the language requested
"""


def _extract_code_and_explanation(text: str, language: str) -> tuple[str, str, str]:
    """Extract code block and explanation from model output."""
    pattern = r"```(\w+)?\n?([\s\S]*?)```"
    matches = re.findall(pattern, text)
    if matches:
        detected_lang = matches[0][0] or language
        code = matches[0][1].strip()
        explanation = re.sub(pattern, "", text).strip()
        return code, detected_lang, explanation
    return text.strip(), language, ""


async def generate_code(
    prompt: str,
    language: str = "",
    context: str = "",
    max_tokens: int = 2048,
    user_id: str = "",
) -> tuple[str, str, str, str, str]:
    """
    Returns (code, language, explanation, provider_name, model_name).
    """
    user_prompt = f"Language: {language}\n\n" if language else ""
    if context:
        user_prompt += f"Context:\n{context}\n\n"
    user_prompt += f"Task:\n{prompt}"

    try:
        text, provider, model = await generate_full_response(
            task="code",
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=max_tokens,
            user_id=user_id,
        )
        code, detected_lang, explanation = _extract_code_and_explanation(text, language)
        return code, detected_lang, explanation, provider, model
    except Exception:
        return "", language, "Code generation unavailable.", "none", ""
