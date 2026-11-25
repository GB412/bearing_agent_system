"""Generate a minimal RoBASCatalog/v1 from *authorized* source ZIP CSV files.

This extracts only material and lubricant options, not bearing models or solver
parameters. It preserves original physical values as strings, without approval.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unsupported CSV encoding; expected UTF-8 or GB18030")


def read_table(archive: zipfile.ZipFile, suffix: str, name_field: str,
               namespace: str, source_id: str) -> tuple[list[dict], dict]:
    matched = [
        path for path in archive.namelist()
        if path.replace("\\", "/").lower().endswith("/" + suffix.lower())
        or path.lower() == suffix.lower()
    ]
    if len(matched) != 1:
        raise ValueError(f"Expected exactly one {suffix} in archive; got {len(matched)}")
    path = matched[0]
    raw = archive.read(path)
    source = decode(raw)
    if not source.strip():
        raise ValueError(f"Empty CSV: {path}")
    dialect = csv.Sniffer().sniff(source[:4096], delimiters=",;\t")
    reader = csv.DictReader(io.StringIO(source), dialect=dialect)
    if not reader.fieldnames or name_field not in reader.fieldnames:
        raise ValueError(
            f"CSV {path} does not contain expected key column {name_field!r}"
        )
    rows: list[dict] = []
    names: set[str] = set()
    for lineno, item in enumerate(reader, start=2):
        if not any(value and value.strip() for value in item.values() if isinstance(value, str)):
            continue
        if None in item:
            raise ValueError(f"Unexpected extra columns at {path}:{lineno}")
        name = item[name_field].strip() if item[name_field] else ""
        if not name or name in names:
            raise ValueError(f"Missing or repeated {name_field} in {path}:{lineno}")
        names.add(name)
        values = {column: (value if value is not None else "")
                  for column, value in item.items() if column != name_field}
        rows.append({
            "id": f"{namespace}:{name}",
            "name": name,
            "values_raw": values,
            "source_fields": {column: column for column in values},
            "source_row": lineno,
            "data_status": "SOURCE_AS_IS",
        })
    if not rows:
        raise ValueError(f"No records found in {path}")
    return rows, {
        "id": source_id, "file": path,
        "sha256": sha(raw), "record_count": len(rows),
    }


def extract(archive_path: Path) -> dict:
    if not archive_path.is_file():
        raise FileNotFoundError(f"Source ZIP missing: {archive_path}")
    raw_zip = archive_path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        materials, material_src = read_table(
            archive, "materialDB.csv", "materialName", "material", "materials"
        )
        lubricants, lubricant_src = read_table(
            archive, "lubricantDB.csv", "oilName", "lubricant", "lubricants"
        )
    return {
        "schema_version": "RoBASCatalog/v1",
        "sources": [material_src, lubricant_src],
        "archive_sha256": sha(raw_zip),
        "materials": materials,
        "lubricants": lubricants,
        # This focused extractor does not claim to import a bearing model DB.
        "bearing_models": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract exact RoBAS materials/lubricants (no physical corrections)"
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = extract(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"Material rows: {len(catalog['materials'])}; "
        f"lubricant rows: {len(catalog['lubricants'])}; "
        f"output: {args.output}"
    )
    print("Values are unreviewed source strings, not validated engineering inputs.")


if __name__ == "__main__":
    main()
