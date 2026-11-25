"""Minimal authorized ZIP importer: identity and source integrity only."""

from __future__ import annotations

import io
import zipfile

import pytest

from bearing_agent_system.catalog_choices import CatalogChoices
from scripts.extract_robas_catalog import extract


def archive(tmp_path, *, material=b"materialName,density(kg/m3)\nSteel,7800\n",
            lubricant=b"oilName,v1(m^2/s)\nOil A,0.001\n"):
    path = tmp_path / "robas.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("RoBAS/Resource/materialDB.csv", material)
        zf.writestr("RoBAS/Resource/lubricantDB.csv", lubricant)
    return path


def test_importer_preserves_raw_source_values_and_exact_ids(tmp_path):
    import json

    catalog = extract(archive(tmp_path))
    assert catalog["schema_version"] == "RoBASCatalog/v1"
    assert catalog["materials"][0]["name"] == "Steel"
    assert catalog["materials"][0]["id"] == "material:Steel"
    assert catalog["materials"][0]["values_raw"]["density(kg/m3)"] == "7800"
    assert catalog["lubricants"][0]["id"] == "lubricant:Oil A"
    assert catalog["bearing_models"] == []
    assert len(catalog["sources"][0]["sha256"]) == 64
    location = tmp_path / "catalog.json"
    location.write_text(json.dumps(catalog), encoding="utf-8")
    resolver = CatalogChoices(location)
    assert resolver.resolve("engineering.materials.inner_ring_id", "Steel") == (
        "material:Steel"
    )
    assert resolver.resolve("engineering.lubrication.lubricant_id", "Oil A") == (
        "lubricant:Oil A"
    )


def test_importer_rejects_duplicate_source_names(tmp_path):
    data = b"materialName,poisson\nSteel,0.3\nSteel,0.28\n"
    with pytest.raises(ValueError, match="repeated"):
        extract(archive(tmp_path, material=data))


def test_importer_rejects_missing_lubricant_column(tmp_path):
    with pytest.raises(ValueError, match="oilName"):
        extract(archive(tmp_path, lubricant=b"name,v1\nOil,0.001\n"))


def test_importer_reads_gb18030_chinese_names(tmp_path):
    material = "materialName,density\n高碳铬轴承钢,7810\n".encode("gb18030")
    catalog = extract(archive(tmp_path, material=material))
    assert catalog["materials"][0]["name"] == "高碳铬轴承钢"


def test_importer_requires_one_file_per_source(tmp_path):
    path = archive(tmp_path)
    with zipfile.ZipFile(path, "a") as zf:
        zf.writestr("other/materialDB.csv", "materialName,density\nSteel2,7800\n")
    with pytest.raises(ValueError, match="exactly one"):
        extract(path)
