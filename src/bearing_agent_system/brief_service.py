"""Future tool ①/② business entrypoints; no model-specific dependencies."""

from __future__ import annotations

from .checks import get_design_status
from .models import DesignBrief, DesignStatus, TrustedContext, UpdateBatch, UpdateResult
from .state_store import SQLiteDesignBriefStore


class DesignBriefService:
    def __init__(self, store: SQLiteDesignBriefStore):
        self.store = store

    def get_brief(self, session_id: str) -> tuple[DesignBrief, int]:
        return self.store.get_brief(session_id)

    def get_design_status(self, session_id: str) -> DesignStatus:
        brief, _ = self.store.get_brief(session_id)
        return get_design_status(brief)

    def update_design_brief(
        self, session_id: str, batch: UpdateBatch, trusted_context: TrustedContext
    ) -> UpdateResult:
        return self.store.apply_updates(session_id, batch, trusted_context)
