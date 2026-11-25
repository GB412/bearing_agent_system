from __future__ import annotations

import json

import pytest

from bearing_agent_system import DesignBriefService, SQLiteDesignBriefStore
from bearing_agent_system.catalog_choices import CatalogChoices


@pytest.fixture
def catalog_path(tmp_path):
    """Synthetic RoBAS identity catalog used only by offline tests."""
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({
        "schema_version": "RoBASCatalog/v1",
        "sources": [],
        "materials": [
            {"id": "material:GCr15", "name": "GCr15",
             "values_raw": {}, "source_fields": {}, "data_status": "SOURCE_AS_IS"},
            {"id": "material:高碳铬轴承钢", "name": "高碳铬轴承钢",
             "values_raw": {}, "source_fields": {}, "data_status": "SOURCE_AS_IS"},
        ],
        "lubricants": [
            {"id": "lubricant:VG32", "name": "VG32",
             "values_raw": {}, "source_fields": {}, "data_status": "SOURCE_AS_IS"}
        ],
        "bearing_models": [],
    }, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def service(tmp_path, catalog_path):
    store = SQLiteDesignBriefStore(
        tmp_path / "brief.sqlite3",
        catalog_choices=CatalogChoices(catalog_path),
    )
    return DesignBriefService(store)
