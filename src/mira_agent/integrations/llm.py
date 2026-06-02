from __future__ import annotations

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from mira_agent.config import Settings
from mira_agent.exceptions import ApiError


def get_model(settings: Settings) -> OpenAIChatModel:
    if settings.llm_provider not in {"openai-compatible", "openai"}:
        raise ApiError(
            "INTEGRATION_NOT_CONFIGURED",
            "Configured LLM provider is not supported.",
            500,
        )
    if not settings.has_llm_config:
        raise ApiError(
            "INTEGRATION_NOT_CONFIGURED",
            "LLM settings are required before running analysis.",
            500,
        )

    provider = OpenAIProvider(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    return OpenAIChatModel(settings.llm_model, provider=provider)
