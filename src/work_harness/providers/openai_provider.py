from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI

from work_harness.config import Settings
from work_harness.providers.base import CompletionResult

logger = logging.getLogger("work_harness.providers.openai")


class OpenAIChatProvider:
    def __init__(self, settings: Settings) -> None:
        kwargs: dict[str, object] = {
            "model": settings.openai_model,
            "temperature": 0,
        }
        if settings.openai_api_key:
            kwargs["api_key"] = settings.openai_api_key
        if settings.openai_api_base:
            kwargs["base_url"] = settings.openai_api_base
        self._model = ChatOpenAI(**kwargs)

    async def complete_json(self, prompt: str, schema: dict) -> CompletionResult:
        logger.debug(
            "OpenAI request: prompt_len=%d schema=%s",
            len(prompt), schema.get("title"),
        )
        try:
            structured = self._model.with_structured_output(schema)
            data = await structured.ainvoke(prompt)
            logger.info(
                "OpenAI completion success: schema=%s",
                schema.get("title"),
            )
            return CompletionResult(content="", data=data)
        except Exception:
            logger.exception(
                "OpenAI completion failed: schema=%s",
                schema.get("title"),
            )
            raise
