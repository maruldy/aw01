from __future__ import annotations

from langchain_openai import ChatOpenAI

from work_harness.config import Settings
from work_harness.providers.base import CompletionResult


class OpenAIChatProvider:
    def __init__(self, settings: Settings) -> None:
        kwargs = {"model": settings.openai_model, "temperature": 0}
        if settings.openai_api_key:
            kwargs["api_key"] = settings.openai_api_key
        if settings.openai_api_base:
            kwargs["base_url"] = settings.openai_api_base
        self._model = ChatOpenAI(**kwargs)

    async def complete_json(self, prompt: str, schema: dict) -> CompletionResult:
        structured = self._model.with_structured_output(schema)
        data = await structured.ainvoke(prompt)
        return CompletionResult(content="", data=data)

