from typing import AsyncGenerator
from fastapi import HTTPException
from services.providers.base_provider import BaseProvider
from services.providers.groq_provider import GroqProvider
from services.providers.ollama_provider import OllamaProvider
from services.providers.nvidia_provider import NvidiaProvider
from services.providers.gemini_provider import GeminiProvider
from services.providers.cerebras_provider import CerebrasProvider
from security.security_logger import log_security_event
from services.rate_limit_service import record_provider_failure, record_provider_success, is_provider_healthy

# Provider registry — single instance of each
PROVIDER_INSTANCES: dict[str, BaseProvider] = {
    "groq": GroqProvider(),
    "ollama": OllamaProvider(),
    "nvidia": NvidiaProvider(),
    "gemini": GeminiProvider(),
    "cerebras": CerebrasProvider(),
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
            {"provider": settings.CV_SECONDARY_PROVIDER,
             "model": settings.CV_SECONDARY_MODEL},
            {"provider": settings.CV_TERTIARY_PROVIDER,
             "model": settings.CV_TERTIARY_MODEL},
            {"provider": settings.CV_FALLBACK_PROVIDER,
             "model": settings.CV_FALLBACK_MODEL},
        ],
        "letter": [
            {"provider": settings.LETTER_PRIMARY_PROVIDER,
             "model": settings.LETTER_PRIMARY_MODEL},
            {"provider": settings.LETTER_SECONDARY_PROVIDER,
             "model": settings.LETTER_SECONDARY_MODEL},
            {"provider": settings.LETTER_TERTIARY_PROVIDER,
             "model": settings.LETTER_TERTIARY_MODEL},
            {"provider": settings.LETTER_FALLBACK_PROVIDER,
             "model": settings.LETTER_FALLBACK_MODEL},
        ],
        "support": [
            {"provider": settings.SUPPORT_PRIMARY_PROVIDER,
             "model": settings.SUPPORT_PRIMARY_MODEL},
            {"provider": settings.SUPPORT_SECONDARY_PROVIDER,
             "model": settings.SUPPORT_SECONDARY_MODEL},
            {"provider": settings.SUPPORT_FALLBACK_PROVIDER,
             "model": settings.SUPPORT_FALLBACK_MODEL},
        ],
        "chat": [
            {"provider": settings.SUPPORT_PRIMARY_PROVIDER,
             "model": settings.SUPPORT_PRIMARY_MODEL},
            {"provider": settings.SUPPORT_SECONDARY_PROVIDER,
             "model": settings.SUPPORT_SECONDARY_MODEL},
            {"provider": settings.SUPPORT_FALLBACK_PROVIDER,
             "model": settings.SUPPORT_FALLBACK_MODEL},
        ],
        "code": [
            {"provider": settings.CODE_PRIMARY_PROVIDER,
             "model": settings.CODE_PRIMARY_MODEL},
            {"provider": settings.CODE_SECONDARY_PROVIDER,
             "model": settings.CODE_SECONDARY_MODEL},
            {"provider": settings.CODE_FALLBACK_PROVIDER,
             "model": settings.CODE_FALLBACK_MODEL},
        ],
    }
    return chains.get(task, chains["support"])


async def generate_full_response(
    task: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    user_id: str = "",
) -> tuple[str, str, str]:
    """
    Tries each provider in the task chain until one succeeds.
    Checks A/B test assignment first when user_id is provided.
    Returns: (response_text, provider_name, model_name)
    """
    # A/B test override — checked before normal chain
    if user_id:
        from services.ab_test_service import get_model_for_user
        ab_assignment = get_model_for_user(task, user_id)
        if ab_assignment:
            ab_provider_name, ab_model = ab_assignment
            ab_provider = PROVIDER_INSTANCES.get(ab_provider_name)
            if ab_provider and ab_provider.is_available():
                try:
                    text = await ab_provider.generate_full(
                        system_prompt, user_prompt, ab_model, temperature, max_tokens
                    )
                    return text, ab_provider_name, ab_model
                except Exception as e:
                    log_security_event(
                        severity="WARNING",
                        event_type="ab_test_provider_error",
                        details={"task": task, "provider": ab_provider_name,
                                 "model": ab_model, "error": str(e)[:200]},
                    )
                    # Fall through to normal chain on failure

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

        if not is_provider_healthy(provider_name):
            continue  # Skip providers known to be unhealthy

        try:
            text = await provider.generate_full(
                system_prompt, user_prompt, model, temperature, max_tokens
            )
            record_provider_success(provider_name)
            return text, provider_name, model

        except Exception as e:
            is_rl = provider.is_rate_limit_error(e)
            record_provider_failure(provider_name, is_rate_limit=is_rl)
            if is_rl:
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
