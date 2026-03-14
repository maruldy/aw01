from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class CompletionResult(BaseModel):
    content: str
    data: dict = Field(default_factory=dict)


class ChatModelProvider(Protocol):
    async def complete_json(self, prompt: str, schema: dict) -> CompletionResult: ...

