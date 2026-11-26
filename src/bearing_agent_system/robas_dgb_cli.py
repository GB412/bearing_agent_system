"""Local CLI: DesignBrief/v2 JSON + five-variable candidate -> RoBAS DATA.txt.

No solver is launched. The user-supplied original DATA and RoBAS resources are
read-only; this utility writes only into the requested output directory.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import DesignBrief
from .robas_dgb_input import DGBProfile, RoBASInputError, build_dgb_data

# Identical to the uploaded original d=40/D=68/B=15 DGB case.
ORIGINAL_DGB_SHA256 = "b6610d150b0b8b05f0d024fe0c6fb90c1d4b270d5ef20f95398d48a6aa165a0f"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create source-compatible DGB DATA.txt without changing the original"
    )
    parser.add_argument("--brief", type=Path, required=True,
                        help="Confirmed DGBDesignBrief/v2 JSON export")
    parser.add_argument("--candidate", type=Path, required=True,
                        help="JSON: Dw_mm, Z, Dpw_mm, fi, fo")
    parser.add_argument("--reference-data", type=Path, required=True,
                        help="Original RoBAS DGB DATA.txt, read-only")
    parser.add_argument("--resources", type=Path, required=True,
                        help="Original RoBAS_Resources/Resource directory containing CSVs")
    parser.add_argument("--out", type=Path, required=True,
                        help="New directory for DATA.txt, manifest and diff")
    parser.add_argument("--reference-sha256", default=ORIGINAL_DGB_SHA256,
                        help="Expected original DATA SHA-256 (default: uploaded DGB case)")
    args = parser.parse_args(argv)

    try:
        brief = DesignBrief.model_validate_json(args.brief.read_text(encoding="utf-8-sig"))
        candidate = json.loads(args.candidate.read_text(encoding="utf-8-sig"))
        if not isinstance(candidate, dict):
            raise RoBASInputError("Candidate JSON must be an object")
        prepared = build_dgb_data(
            brief=brief,
            candidate=candidate,
            reference_data=args.reference_data,
            material_csv=args.resources / "materialDB.csv",
            lubricant_csv=args.resources / "lubricantDB.csv",
            profile=DGBProfile(reference_sha256=args.reference_sha256),
        )
        output = prepared.write(args.out)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(status=2, message=f"RoBAS DATA generation failed: {exc}\n")
    print(f"Generated: {output}")
    print(f"Reference SHA-256: {prepared.manifest['reference_sha256']}")
    print(f"DATA SHA-256: {prepared.manifest['output_sha256']}")
    print(f"Changed fields: {len(prepared.manifest['changed_fields'])}")
    print("Note: valid DATA format does not prove solver convergence or engineering fitness.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
