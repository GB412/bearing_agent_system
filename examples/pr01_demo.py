"""Demonstrate structured, trusted updates (not natural-language extraction)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from bearing_agent_system import (
    DesignBriefService,
    SQLiteDesignBriefStore,
    TrustedContext,
    UpdateBatch,
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dgb-pr01-") as tmp:
        db_path = Path(tmp) / "brief.sqlite3"
        service = DesignBriefService(SQLiteDesignBriefStore(db_path))
        batch = UpdateBatch.model_validate(
            {
                "operation": "set",
                "changes": [
                    {"path": "dimensions.d_mm", "value": 25, "unit": "mm", "evidence_span": "25×52×15"},
                    {"path": "dimensions.D_mm", "value": 52, "unit": "mm", "evidence_span": "25×52×15"},
                    {"path": "dimensions.B_mm", "value": 15, "unit": "mm", "evidence_span": "25×52×15"},
                    {"path": "operating.inner_speed_rpm", "value": 18000, "unit": "rpm", "evidence_span": "内圈18000rpm"},
                    {"path": "operating.axial_load_n", "value": 0, "unit": "N", "evidence_span": "无轴向载荷"},
                ],
            }
        )
        result = service.update_design_brief(
            "dgb-demo",
            batch,
            TrustedContext(message_id="message-1", user_message="尺寸25×52×15，内圈18000rpm，无轴向载荷"),
        )
        print("UPDATE:", result.model_dump_json(indent=2))
        # Re-open using a fresh store connection to demonstrate persistence.
        restored, revision = SQLiteDesignBriefStore(db_path).get_brief("dgb-demo")
        print("RESTORED REVISION:", revision)
        print("BRIEF:", json.dumps(restored.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
