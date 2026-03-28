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

    async def generate_with_tools(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """
        Agentic tool-use loop.

        Supports a single tool: ``web_search`` (backed by Tavily).
        Keeps calling the model until it stops requesting tool calls,
        then returns the final text response.
        """
        import json
        from groq import AsyncGroq
        from config import settings
        from services.search_service import search as tavily_search

        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        current_messages = list(messages)

        for _ in range(5):  # guard against infinite loops
            response = await client.chat.completions.create(
                model=model,
                messages=current_messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = response.choices[0]

            if choice.finish_reason != "tool_calls":
                return choice.message.content or ""

            # Append assistant message with tool_calls
            current_messages.append(choice.message.model_dump(exclude_none=True))

            # Execute each tool call
            for tc in choice.message.tool_calls or []:
                if tc.function.name == "web_search":
                    try:
                        args = json.loads(tc.function.arguments)
                        query = args.get("query", "")
                    except Exception:
                        query = ""
                    result = await tavily_search(query)
                    current_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result or "No results found.",
                        }
                    )

        # Fallback: one last call without tools
        fallback = await client.chat.completions.create(
            model=model,
            messages=current_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return fallback.choices[0].message.content or ""
