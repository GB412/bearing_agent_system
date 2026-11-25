"""Exact RoBAS option identity for trusted material and lubricant fields.

No aliases, fuzzy matching, ranking, or implicit engineering approval here.
Only original catalog names and IDs may resolve to a canonical record ID.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .parameter_catalog import InvalidChange

CATALOG_FIELDS: dict[str, str] = {
    "engineering.materials.inner_ring_id": "materials",
    "engineering.materials.outer_ring_id": "materials",
    "engineering.materials.ball_id": "materials",
    "engineering.cage.material_id": "materials",
    "engineering.lubrication.lubricant_id": "lubricants",
}


class CatalogChoices:
    """Small read-only identity check reused by writes and recommendations."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(
            path if path is not None else os.environ.get(
                "ROBAS_CATALOG_PATH", ".bearing_agent/robas_catalog.json"
            )
        )

    def resolve(self, field: str, value: str) -> str:
        """Return exactly the installed catalog ID or reject the option.

        A raw catalog name is accepted for the user-facing tool. The canonical
        ID is also accepted internally when adopting a stored proposal.
        """
        table = CATALOG_FIELDS.get(field)
        if table is None:
            raise InvalidChange(f"Not a catalog-backed selection: {field}")
        if not isinstance(value, str) or not value.strip():
            raise InvalidChange("Catalog choice needs a nonempty exact name or ID")
        if not self.path.is_file():
            raise InvalidChange(
                "CATALOG_UNAVAILABLE: RoBAS catalog is not installed; "
                "cannot confirm material or lubricant"
            )
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("schema_version") != "RoBASCatalog/v1":
                raise ValueError("Unsupported RoBAS catalog version")
            rows = data[table]
            if not isinstance(rows, list):
                raise ValueError("Catalog table must be a list")
            ids: set[str] = set()
            names: set[str] = set()
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("Invalid catalog row")
                item_id, name = row.get("id"), row.get("name")
                if not isinstance(item_id, str) or not item_id.strip():
                    raise ValueError("Invalid catalog ID")
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("Invalid catalog name")
                if item_id in ids or name in names:
                    raise ValueError("Ambiguous duplicate catalog ID or name")
                ids.add(item_id)
                names.add(name)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise InvalidChange(
                "CATALOG_ERROR: cannot validate installed RoBAS catalog"
            ) from exc
        requested = value.strip()
        matches = [
            row for row in rows
            if requested == row["id"] or requested == row["name"]
        ]
        if len(matches) != 1:
            raise InvalidChange(
                f"CATALOG_NOT_FOUND: {requested!r} is not an exact {table} "
                "catalog name or ID; ask the user to select a listed name"
            )
        return matches[0]["id"]
