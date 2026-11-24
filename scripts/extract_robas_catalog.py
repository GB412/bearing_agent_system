"""Extract unchanged materials, lubricants and bearing records from RoBAS ZIP.

No plausibility filtering, silent correction or inferred units. The JSON output
is generated locally and should not be committed if its license forbids sharing.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

MATERIAL_FIELDS = {
    "elsaModules(Pa)": "elastic_modulus_pa",
    "density(kg/m3)": "density_kg_m3",
    "heatConductivity(w/m/k)": "thermal_conductivity_w_mk",
    "linearExpan(1/k)": "thermal_expansion_per_k",
    "poisson": "poisson_ratio",
    "specificHeat": "specific_heat_j_kgk",
}
LUBRICANT_FIELDS = {
    "density0": "density0",
    "t1(degC)": "t1_c",
    "v1(m^2/s)": "v1_m2_s",
    "t2(degC)": "t2_c",
    "v2(m^2/s)": "v2_m2_s",
    "slopeDensity": "slope_density",
    "specificHeat0(J/kg/degC)": "specific_heat0_j_kg_c",
    "slopeCp": "slope_cp",
}
BEARING_FIELDS = {
    "d": "d_mm", "D_": "D_mm", "B": "B_mm",
    "C": "C_source", "C0": "C0_source",
    "nmax": "nmax_source", "nr": "nr_source",
}


def _rows(blob: bytes, key: str, mapping: dict[str, str], prefix: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))))
    if not rows:
        raise ValueError(f"{prefix}: empty source")
    required = {key, *mapping}
    if not required.issubset(rows[0]):
        raise ValueError(f"{prefix}: missing columns {required - set(rows[0])}")
    used = set()
    result = []
    for number, row in enumerate(rows, 2):
        name = row[key]
        if not name or name in used:
            raise ValueError(f"{prefix}: blank or duplicate name at row {number}")
        used.add(name)
        result.append({
            "id": f"{prefix}:{name}", "name": name, "source_row": number,
            "values_raw": {dest: row[src] for src, dest in mapping.items()},
            "source_fields": {dest: src for src, dest in mapping.items()},
            "data_status": "SOURCE_AS_IS",
        })
    return result


def _models(blob: bytes) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="robas-source-") as directory:
        path = Path(directory) / "bearing.db"
        path.write_bytes(blob)
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            available = {col[1] for col in db.execute('PRAGMA table_info("T_SKFA01")')}
            required = {"ID", "Type", *BEARING_FIELDS}
            if not required.issubset(available):
                raise ValueError(f"T_SKFA01 missing columns {required - available}")
            db.row_factory = sqlite3.Row
            records = []
            for row in db.execute('SELECT * FROM "T_SKFA01" ORDER BY "ID"'):
                records.append({
                    "id": f"T_SKFA01:{row['ID']}", "name": str(row["Type"]),
                    "source_table": "T_SKFA01", "source_pk": row["ID"],
                    "values_raw": {
                        dest: row[src] for src, dest in BEARING_FIELDS.items()
                    },
                    "source_fields": dict((dest, src) for src, dest in BEARING_FIELDS.items()),
                    "data_status": "SOURCE_AS_IS",
                })
            return records
        finally:
            db.close()


def extract(archive: Path) -> dict:
    paths = {
        "materials": "RoBAS_Resources/Resource/materialDB.csv",
        "lubricants": "RoBAS_Resources/Resource/lubricantDB.csv",
        "bearing_models": "RoBAS_Resources/Data/bearing.db",
    }
    sources = []
    with zipfile.ZipFile(archive) as z:
        contents = {}
        for category, path in paths.items():
            content = z.read(path)
            contents[category] = content
            sources.append({
                "id": category, "archive_member": path,
                "sha256": hashlib.sha256(content).hexdigest(),
            })
    return {
        "schema_version": "RoBASCatalog/v1",
        "source_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "data_policy": "SOURCE_AS_IS_NO_PLAUSIBILITY_FILTER",
        "sources": sources,
        "materials": _rows(contents["materials"], "materialName", MATERIAL_FIELDS, "material"),
        "lubricants": _rows(contents["lubricants"], "oilName", LUBRICANT_FIELDS, "lubricant"),
        "bearing_models": _models(contents["bearing_models"]),
        "notes": [
            "All numerical data are copied from original source rows.",
            "C/C0/nmax raw column values have not been converted into inferred units.",
            "Source record existence is not engineering suitability confirmation.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = extract(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"materials={len(data['materials'])}; lubricants={len(data['lubricants'])}; "
          f"bearing_models={len(data['bearing_models'])}; output={args.output}")


if __name__ == "__main__":
    main()
