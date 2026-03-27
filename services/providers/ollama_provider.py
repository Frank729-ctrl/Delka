import json
from typing import AsyncGenerator
import httpx
from fastapi import HTTPException
from services.providers.base_provider import BaseProvider


class OllamaProvider(BaseProvider):

    def is_available(self) -> bool:
        from config import settings
        return bool(settings.OLLAMA_BASE_URL)

    def is_rate_limit_error(self, error: Exception) -> bool:
        return False  # Ollama is local — never rate limited

    async def generate_full(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        from config import settings
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=settings.OLLAMA_TIMEOUT_SECONDS
            ) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="LLM service unavailable.")
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"LLM service error: {exc.response.status_code}",
            )

        try:
            return response.json()["message"]["content"]
        except (KeyError, ValueError):
            raise HTTPException(
                status_code=500, detail="Malformed response from LLM service."
            )

    async def generate_stream(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.8,
    ) -> AsyncGenerator[str, None]:
        from config import settings
        payload = {
            "model": model,
            "stream": True,
            "messages": messages,
            "options": {"temperature": temperature},
        }
        try:
            async with httpx.AsyncClient(
                timeout=settings.OLLAMA_STREAM_TIMEOUT_SECONDS
            ) as client:
                async with client.stream(
                    "POST",
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json=payload,
                ) as response:
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token

                        if chunk.get("done") is True:
                            break
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="LLM service unavailable.")
