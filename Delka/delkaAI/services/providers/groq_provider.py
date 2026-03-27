from typing import AsyncGenerator
from services.providers.base_provider import BaseProvider


class GroqProvider(BaseProvider):

    def is_available(self) -> bool:
        from config import settings
        return bool(settings.GROQ_API_KEY)

    def is_rate_limit_error(self, error: Exception) -> bool:
        try:
            import groq
            if isinstance(error, groq.RateLimitError):
                return True
        except ImportError:
            pass
        error_str = str(error).lower()
        return "429" in error_str or "rate_limit" in error_str or "rate limit" in error_str

    async def generate_full(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        from groq import AsyncGroq
        from config import settings
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    async def generate_stream(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.8,
    ) -> AsyncGenerator[str, None]:
        from groq import AsyncGroq
        from config import settings
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        async for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token
