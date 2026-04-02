"""
NVIDIA NIM provider — OpenAI-compatible API at integrate.api.nvidia.com.
Uses the openai SDK with a custom base_url.
"""
from typing import AsyncGenerator
from services.providers.base_provider import BaseProvider


class NvidiaProvider(BaseProvider):

    def is_available(self) -> bool:
        from config import settings
        return bool(settings.NVIDIA_API_KEY)

    def is_rate_limit_error(self, error: Exception) -> bool:
        error_str = str(error).lower()
        return "429" in error_str or "rate_limit" in error_str or "rate limit" in error_str

    def _client(self):
        from openai import AsyncOpenAI
        from config import settings
        return AsyncOpenAI(
            api_key=settings.NVIDIA_API_KEY,
            base_url=settings.NVIDIA_BASE_URL,
        )

    async def generate_full(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        client = self._client()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def generate_stream(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.8,
    ) -> AsyncGenerator[str, None]:
        client = self._client()
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
