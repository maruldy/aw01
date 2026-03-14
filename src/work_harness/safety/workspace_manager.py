from __future__ import annotations

from pathlib import Path

from work_harness.config import Settings


class WorkspaceManager:
    def __init__(self, settings: Settings) -> None:
        self._root = settings.managed_workspace_root
        self._root.mkdir(parents=True, exist_ok=True)

    async def prepare(self, work_item_id: str) -> Path:
        workspace = self._root / work_item_id
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

