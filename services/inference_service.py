from typing import AsyncGenerator
from fastapi import HTTPException
from services.providers.base_provider import BaseProvider
from services.providers.groq_provider import GroqProvider
from services.providers.ollama_provider import OllamaProvider
from security.security_logger import log_security_event

# Provider registry — single instance of each
PROVIDER_INSTANCES: dict[str, BaseProvider] = {
    "groq": GroqProvider(),
    "ollama": OllamaProvider(),
}


def get_task_chain(task: str) -> list[dict]:
    """
    Returns ordered list of {provider, model} dicts for a task.
    First entry = primary. Second entry = fallback.
    Reads from settings so .env controls everything.
    """
    from config import settings
    chains = {
        "cv": [
            {"provider": settings.CV_PRIMARY_PROVIDER,
             "model": settings.CV_PRIMARY_MODEL},
            {"provider": settings.CV_FALLBACK_PROVIDER,
             "model": settings.CV_FALLBACK_MODEL},
        ],
        "letter": [
            {"provider": settings.LETTER_PRIMARY_PROVIDER,
             "model": settings.LETTER_PRIMARY_MODEL},
            {"provider": settings.LETTER_FALLBACK_PROVIDER,
             "model": settings.LETTER_FALLBACK_MODEL},
        ],
        "support": [
            {"provider": settings.SUPPORT_PRIMARY_PROVIDER,
             "model": settings.SUPPORT_PRIMARY_MODEL},
            {"provider": settings.SUPPORT_FALLBACK_PROVIDER,
             "model": settings.SUPPORT_FALLBACK_MODEL},
        ],
    }
    return chains.get(task, chains["support"])


async def generate_full_response(
    task: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> tuple[str, str, str]:
    """
    Tries each provider in the task chain until one succeeds.
    Returns: (response_text, provider_name, model_name)
    """
    chain = get_task_chain(task)

    for entry in chain:
        provider_name: str = entry["provider"]
        model: str = entry["model"]

        provider = PROVIDER_INSTANCES.get(provider_name)
        if provider is None:
            log_security_event(
                severity="WARNING",
                event_type="provider_unknown",
                details={"task": task, "provider": provider_name},
            )
            continue

        if not provider.is_available():
            continue

        try:
            text = await provider.generate_full(
                system_prompt, user_prompt, model, temperature, max_tokens
            )
            return text, provider_name, model

        except Exception as e:
            if provider.is_rate_limit_error(e):
                next_providers = [
                    c["provider"] for c in chain
                    if c["provider"] != provider_name
                ]
                log_security_event(
                    severity="WARNING",
                    event_type="provider_rate_limited",
                    details={
                        "task": task,
                        "provider": provider_name,
                        "model": model,
                        "switching_to": next_providers[0] if next_providers else "none",
                    },
                )
            else:
                log_security_event(
                    severity="WARNING",
                    event_type="provider_error",
                    details={
                        "task": task,
                        "provider": provider_name,
                        "model": model,
                        "error": str(e)[:200],
                    },
                )
            continue

    raise HTTPException(
        status_code=503,
        detail="All inference providers unavailable. Try again later.",
    )


async def generate_stream_response(
    task: str,
    messages: list[dict],
    temperature: float = 0.8,
) -> AsyncGenerator[str, None]:
    """
    Tries each provider in the task chain for streaming.
    Attempts connection before yielding anything, then yields tokens.
    """
    chain = get_task_chain(task)

    for entry in chain:
        provider_name: str = entry["provider"]
        model: str = entry["model"]

        provider = PROVIDER_INSTANCES.get(provider_name)
        if provider is None:
            continue

        if not provider.is_available():
            continue

        try:
            # Collect first token to verify connection before yielding
            gen = provider.generate_stream(messages, model, temperature)
            first_token = None
            async for token in gen:
                first_token = token
                break

            if first_token is not None:
                yield first_token
                async for token in gen:
                    yield token
            return

        except Exception as e:
            if provider.is_rate_limit_error(e):
                log_security_event(
                    severity="WARNING",
                    event_type="provider_rate_limited",
                    details={"task": task, "provider": provider_name, "model": model},
                )
            else:
                log_security_event(
                    severity="WARNING",
                    event_type="provider_error",
                    details={
                        "task": task,
                        "provider": provider_name,
                        "model": model,
                        "error": str(e)[:200],
                    },
                )
            continue

    yield "data: [ERROR]\n\n"
