from abc import ABC, abstractmethod
from typing import AsyncGenerator


class BaseProvider(ABC):

    @abstractmethod
    async def generate_full(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a complete response. Returns full text string."""
        ...

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.8,
    ) -> AsyncGenerator[str, None]:
        """Generate a streaming response. Yields token strings."""
        ...

    @abstractmethod
    def is_rate_limit_error(self, error: Exception) -> bool:
        """
        Returns True if this error is a rate limit (HTTP 429).
        Used by inference_service to trigger immediate fallback
        instead of waiting for timeout.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """
        Returns True if this provider is properly configured.
        Example: Groq returns False if GROQ_API_KEY is empty.
        inference_service skips unavailable providers entirely.
        """
        ...
