# CALC-01 — DGB five-variable geometry derivation (source-backed baseline)

## Scope and provenance

A small **deterministic numerical component**, not an Agent, optimizer, RoBAS
executable runner, DATA writer, 3-D CAD, or engineering certification.

- Main implementation: `src/bearing_agent_system/dgb_geometry.py`.
- Input: `{"d_mm": 50, "D_mm": 110, "B_mm": 27}` and
  `{"Dw_mm": 15, "Z": 11, "Dpw_mm": 80, "fi": 0.52, "fo": 0.54}`.
- Output: frozen `DerivedDGBGeometry` with `DerivedCageGeometry`;
  coordinates and dimensions are in **mm**, except dimensionless coefficients.
- Geometry rule ID: `robas-dgb-c0-source-v1`.
- Golden case is the audited **d40/D68/B15, Dw8.334/Z11/Dpw54** original
  DGB DATA, which yields inner/outer sidewalls **49.00/59.02 mm** and
  StraightPocketCage OD/ID/width **58.92/53.92/11 mm**.
- Original C# source supplied with the project:
  `RoBAS/Core/BallBearing/DeepGroveBallBearing/DGBGeometry.cs:53-98`;
  `RoBAS/Core/BallBearing/DeepGroveBallBearing/DGBOptimizer.cs:566-604`;
  `RoBAS/BearingModel/Race/InnerRace/SingleRowDeepGrooveInnerRace.cs:88-106`;
  `RoBAS/BearingModel/Race/OuterRace/SingleRowDeepGrooveOuterRace.cs:91-113`;
  `RoBAS/BearingModel/Cage/StraightPocketCage.cs:39-50,113-129`.
  Existing Python corroboration: `GB412/Bearing_CAD`
  `robas_sizing.py`, `robas_ball_input.py`, `drawing_legacy_design.py`.

**Use of the source does not validate physical applicability, strength,
fatigue life, lubrication, or manufacturability.** This reproduction does not
import or invoke the original DGB optimizer.

## Adopted numerical choices

For bore `d`, legacy C0 geometry clearance is from the original table,
`10 <= d < 200 mm` only. At `d=50 mm` it is **0.017 mm**.
The shoulder factor `k=0.35` for `d<=25`, otherwise `k=0.40`.

Using the source getter precision (ball to 0.001 mm, pitch/grooves/shoulders
to 0.01 mm), calculate:

- Inner groove diameter `di = Dpw - Dw`.
- Outer groove diameter `De = Dpw + Dw + Gr`.
- Inner shoulder `d2 = di + k*Dw`.
- Outer shoulder `D2 = De - k*Dw`.
- Analysis inner-race outside diameter `= d2`, for this specific
  single-row inner-race constructor.
- Inner/outer groove radii `fi*Dw`, `fo*Dw`.
- `Z`-dependent element indices `(1,Z+1,0,0,0,0)`.
- StraightPocketCage pocket, guide gap, ring diameters, width, and
  guide dimensions use the exact source-order getter and formula sequence.

The source `DGBGeometry` class has a known metre/millimetre discrepancy
when adding `CalcuRadialClearance` into the outer groove. This code
uses the source-compatible **millimetre** scalar inner/outer race path.
It deliberately accepts `Dpw` independent of `(d + D)/2`: this is
necessary for the user-selected five-parameter design space.

`Gr` here is a **geometry rule value**, not `freeIntCls` from DATA;
CALC-02 must source `freeIntCls` independently.

## Prescreen only

Checks include finite/positive values, integer Z and the existing <=64
source-case limit, curvature factors >0.5, ball non-overlap, rim and raceway
envelopes, shoulder/raceway intersections, positive cage guidance clearances,
pocket spacing and cage width. Invalid input raises `DGBGeometryError`
with a stable `code`. **No invented min-wall-thickness or engineering
clearance thresholds** are added.

The StraightPocketCage is an **analysis cage**, not a guarantee that the
user-selected stamped/steel cage is an equivalent manufactured structure.
Cage material is deliberately left to CALC-02.

## Local checks

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_calc01_dgb_geometry.py
python -m pytest -q tests -m "not live"
ruff check .
```

No API key, Windows, RoBAS EXE, or CAD libraries are required.
Run the following after the new module is available:

```python
from bearing_agent_system.dgb_geometry import derive_dgb_geometry
result = derive_dgb_geometry(
    {"d_mm": 50, "D_mm": 110, "B_mm": 27},
    {"Dw_mm": 15, "Z": 11, "Dpw_mm": 80, "fi": .52, "fo": .54},
)
print(result)
```

## Non-goals and next gate

CALC-02 must map `DesignBrief/v2` + a complete candidate + a checked
reference DATA to a 43-record/324-field file. It requires access to an
original **DGB DATA** file, accurate material and lubricant resource CSVs,
and an explicit field-level inheritance decision. Technical baseline input
is **not** engineering-ready input.

No `DATA.txt`, solver run, thermal prediction or fatigue-life validation
is claimed in this PR. The optimized `fi/fo` must be applied explicitly to
`raceCurFac1/2` by CALC-02, avoiding the original C# backing-field
setter disconnect.
