# Repository Guidelines

## Project Structure & Module Organization

FreeCAD concept model of a turntable with one downward-facing woofer, two front full-range satellites, a shared transformer, and an amplifier including its heatsink. The selected curved-arm mechanism has a separate fit-study assembly; installation is not released.

- `tools/build_model.py`: geometry generation and CAD export; `tools/ac_inlet.py`: rear AC inlet opening and conservative installation/wiring volumes.
- `tools/feet.py`: purchased foot assemblies, upward-barrel mounts, bottom-panel through holes and assumed blind screw pilots; `tests/test_feet.py`: saved geometry, collisions and chamber-leak regression checks.
- `tools/hinges.py`: HFA5751-3434 fixed/moving leaves, cover spacers/backing plates and mounting holes; `tests/test_hinges.py`: saved holes, blind-depth and moving-assembly collision checks. Vendor sources and assumptions are in `references/hinges/README.md`.
- `tools/fascia.py`: selected T extrusion and the acoustic-roof front rebate; `tests/test_fascia.py`: saved section, residual shelf, neighbor clearance and chamber-seal regressions. Vendor dimensions and installation assumptions are in `references/fascia/README.md`.
- `tools/build.FCMacro`: GUI entry point; invokes generation, rendering, and dimension-sheet creation.
- `tools/render_views.py` and `tools/dimension_sheet.py`: viewport previews, temporary foot-installation and hinge-installation details, and projected drawings. Detail geometry is never saved into the source CAD.
- `tools/drawing_data.py` and `tools/drawing_pack.py`: saved-solid projection data and three grouped A3 PDF books under `output/pdf/`; see `docs/drawing-pack.md` for the separate FreeCAD/PDF runtimes.
- `tools/drawing_details.py`: six panel hole schedules (including the rear cover wall), the baffle front-face projection and a temporary midline assembly section; `tools/drawing_detail_pages.py`: their PDF layouts. Preserve existing part drawing IDs when adding detail pages. Section geometry is never saved into source CAD.
- `tools/assembly-guide.FCMacro`, `tools/assembly_guide.py`, and `tools/assembly_guide_pdf.py`: read-only CAD rendering and the two-page A2 numbered guide; see `docs/assembly-guide.md`. Covers the selected study's physical objects exactly once; exploded placements are temporary and never saved over source CAD.
- `tools/validate_model.py`: baseline geometry and STEP validation; `tests/test_regressions.py`: regression tests; `tests/test_ac_inlet.py`: rear inlet opening and wiring-space checks.
- `tools/mechanism_study.py` and `tools/mechanism-study.FCMacro`: selected-mechanism assembly, fit report, and GUI previews; `tests/test_mechanism_study.py`: fit-study regression tests.
- `cad/parameters.json`: cabinet, drivers, transformer, amplifier, AC inlet, feet, T-fascia and hinge installation inputs; `lumi-three-driver.FCStd` / `.step`, `parts.csv`, and `validation.json` are baseline outputs.
- `cad/wood-cut-list.csv`: generated integer rectangular stock sizes and quantities. `StockLength` / `StockWidth` / `StockThickness` are board-local dimensions; tilted XYZ envelopes and finished bevels may remain fractional.
- `cad/selected-mechanism.json`: mechanism assumptions; `lumi-selected-mechanism-fit.FCStd` / `.step` and `mechanism-fit-report.json` are fit-study outputs. The study reads the saved baseline FCStd. Historical `lumi-dual-driver.*` files are available only in Git history.
- `previews/`: generated PNG and SVG assets.
- `docs/audio-layout.md`: chamber volumes, trial ports, and unimplemented satellite-port options; `docs/current-work-handoff.md`: verified resume state.
- `docs/design-basis.md`: dimension sources and manufacturing limitations; `docs/selected-mechanism.md`: fit-study assumptions, rebuild sequence, and remaining installation work. Reference images are under `references/`.

## Build, Test, and Development Commands

Use FreeCAD 1.1.1. Run commands from the repository root.

For macOS terminal commands, set `FREECAD_RESOURCES` to the installed FreeCAD application's `Contents/Resources` directory, containing `bin/python` and `lib`; see [README](README.md#v09-基线重建). Use repository-relative paths for project files and links. Keep machine-specific installation paths out of documentation; use runtime variables for external tools.

```sh
open -a FreeCAD --args "$PWD/tools/build.FCMacro"
```

On macOS, this starts generation when FreeCAD is closed. Otherwise, execute the macro through FreeCAD's Macro dialog. Save manual edits separately and close the baseline file before rebuilding, including reopened files whose document names differ from `LumiThreeDriver`; the baseline generator only guards that document name. The macro does not run validation; run it separately afterward.

```sh
PYTHONPATH="${FREECAD_RESOURCES:?请先设置 FreeCAD 运行环境}/lib" \
  "$FREECAD_RESOURCES/bin/python" tools/validate_model.py
git diff --check
```

Validation checks the parameter snapshot and required installation fields before geometry. A failed preflight writes `passed: false` and `errors` to `cad/validation.json`, replacing any previous success report, then exits nonzero. The validator closes the document it opened. Substitute `tools/build_model.py` to regenerate CAD and the parts list without GUI colors, previews, or a refreshed validation report.

After baseline changes, rebuild and validate the baseline first, then execute `tools/mechanism-study.FCMacro` in FreeCAD. Save manual edits separately and close the study output before rebuilding; the study guards both document name and resolved output path. Its macro regenerates the study, report, and two previews, while `tools/mechanism_study.py` alone generates no GUI previews. The study report records the baseline SHA-256. Do not delete the baseline FCStd while this dependency remains.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions and JSON keys, and stable descriptive CAD object IDs such as `TweeterLeft`. Preserve Chinese user-facing labels. All geometry uses millimetres; suffix reported measurements with `_mm` where appropriate. Resolve paths from script locations. No formatter or linter is configured.

## Testing Guidelines

Use FreeCAD’s Python to run `-m unittest discover -s tests -v`. Tests use temporary directories. Validation uses FreeCAD and Open CASCADE; no coverage threshold is configured. Add descriptive boolean checks for changed dimensions, mounting clearances, chamber closure, port airflow, or export behavior. Read exact dimensions with `optimalBoundingBox(False)` so GUI tessellation does not change dimension checks. After geometry changes, regenerate deliverables, run validation, and visually inspect affected previews. Export leaf `Part::Feature` objects only to avoid duplicated group geometry.

Drawing changes require `tests/test_drawing_pack.py` in FreeCAD and `tests/test_drawing_pdf.py` in a regular Python runtime with `reportlab`, `svglib`, `pypdf` and `pdfplumber`. Run `-m unittest discover -s tests -p '*_pdf.py' -v` there to include the assembly guide checks. Pass `FREECAD_RESOURCES` in that process environment to include the full CAD-extraction/PDF-CLI regression; it writes only temporary outputs and verifies all three position tables and retained part drawing IDs. Regenerate drawing data before composing PDFs after extraction changes; inspect affected pages with Poppler. Hole schedules use formed-panel datums: baffle S is distance along the front face, while the bottom view displays +Y downward. Preserve blind-hole depth, recess machining face and unconfirmed mounting-hole notes. A-H02 includes rear-face blind wood pilots; A-H03 isolates the cover rear wall and must not imply through-drilling the front wall.

## Commit & Pull Request Guidelines

Follow the existing concise English Angular-style commit messages, such as `feat(cad): ...`, `fix: ...`, or `docs: ...`. PRs should explain dimension changes, assumptions, validation results, and relevant issues, with before/after previews for geometry changes. Include regenerated artifacts alongside their source changes; exclude ignored backups and logs.

## Modeling Boundaries

Edit `cad/parameters.json` and rebuild: saved `Part::Feature` solids do not update automatically. Validation rejects mismatched or missing parameter snapshots. The SC-2103 layout has three independent chambers and a replaceable rear port; `fullrange` is the parameter/role name, while `TweeterLeft` / `TweeterRight` remain stable legacy object IDs. CAD cavity volumes and trial port dimensions are not verified acoustic tuning. Driver `total_height` includes `flange_thickness`; inward depth is their difference. Amplifier dimensions already include the heatsink. Transformer ear width/thickness, speaker cutouts, mounting holes, and amplifier floor clearance remain assumptions. Distinguish user-provided dimensions from estimates. Passing geometry checks does not establish acoustic performance or manufacturing readiness. Reference photos retain their owners' copyright; the repository license does not cover them.

The bottom panel includes its front edge; do not recreate the fully overlapping `LowerRail` as a separate part. Its former A-P03 left drawing slot and W05 guide code are retired; preserve the other drawing and guide IDs. Slat clearance checks include `Bottom`.

The v0.5 woodworking layout uses a 450 × 350 mm footprint. `acoustic.baffle_thickness` and `slat_thickness` are true normal thicknesses; baffle horizontal cuts and adjoining divider fronts must stay geometrically coincident. Slats have rectangular `slat_face_width` × `slat_thickness` sections and a vertical `slat_pitch`. Integer stock dimensions do not define kerf, measured sheet thickness, finish allowances, or joint clearances; do not round mating geometry independently.

`deck_rear_clearance` controls the nominal gap between `FloatingDeck` and the inner face of `Back`; the default is 2 mm. The deck is 418 × 328 × 6 mm, with front Y=8, rear Y=336 and back inner face Y=338; side gaps remain 4 mm each. Changing the rear gap changes deck depth without moving the spindle hole, supports or deck height. Rebuild both assemblies, stock lists, previews, drawings B-P04/B-H03 and the W11 guide entry after changes. This is an installation assumption, not verified suspension travel or a released fit; keep the deck mechanically isolated from the back.

The v0.6 AC inlet is a horizontally mounted 8-F5 candidate: 48 × 28 mm R3 opening, two Ø4.5 holes with vertical pitch 40 mm, centre X=70/Z=88.5 after lowering 16 mm for symmetric hinges in v0.9. The transformer moves forward 10 mm to Y=267; keep the 20 mm wiring reservation, with 6.72 mm transformer clearance. The flange extends 1.88 mm beyond the 350 mm cabinet depth. Original vendor images and unverified electrical/installation conditions are in `references/ac-inlet/README.md`; the combined image is a reading aid, not dimension authority. C8 provides no protective earth. Geometry validation does not release mains wiring or the 12 mm panel fastening design.

Keep inlet and power-cord purchase URLs and SKU IDs in `references/ac-inlet/README.md`. Recording a product link does not verify its specifications. The power cord and external plug are not modeled or included in the current overall dimensions.

The v0.7 feet use purchased Ø30 × 20 rubber feet with M8 × 23 exposed studs and Ø37 × 2.5 flanges with Ø12 × 14.5 upward barrels. `tools/feet.py` drives four assemblies and bottom-panel holes. Nominal uncompressed floor height is 22.5 mm; cabinet height remains 124 mm, closed overall height is 210.7 mm. Foot centres are X=33/417, Y=40/320. Mount PCD Ø28, panel clearance Ø12.4, and Ø3 × 8 blind wood-screw pilots are assumptions; fastener head clearance, thread engagement, sealing and load remain unverified. Preserve the vendor images, purchase URLs and SKU IDs in `references/feet/README.md`. The 19.5 mm woofer ground clearance is below the previous 20 mm trial target; geometry validation records this separately and does not establish acoustic adequacy.

`foot_height` must equal `feet.rubber_height + feet.flange_thickness` for the supported flush-contact installation. Changing foot dimensions does not automatically translate the other absolute Z parameters; update the linked heights described in `references/feet/README.md` and rebuild both CAD files and their drawings. Spacers or a different mount orientation require a geometry change, not just a new `foot_height` value. Chamber closure includes the saved foot and mount solids in ideal contact; it is not proof of real thread or panel sealing.

The v0.8 fascia uses the selected 30 × 30 × 5 mm aluminium T extrusion, broad face forward and centred web rearward. `tools/fascia.py` drives the 425 mm strip and the roof rebate. Each end gap is 0.5 mm; fit/bedding clearance is 0.2 mm (assumptions). Roof front Y=5.2, rebate rear Y=30.2, depth 3.7, residual thickness 4.3 mm. Preserve the baffle seal behind the rebate. Roof drilling datums follow the new formed front edge (bearing local Y=166.8, global Y=172). Keep drawing IDs A-P02 (fascia), B-P01 (roof), A-03 (section) and B-H02 (roof drilling/rebate). Clearance is not a modeled adhesive layer or a confirmed root-radius allowance. Keep vendor image, URL and SKU in `references/fascia/README.md`; root radii, adhesive and retention remain unconfirmed.

The v0.9 selected HFA5751-3434 hinges use symmetric X=100/350 (100 mm from each cabinet side), with 5.5 mm clearance above the lowered AC flange; shared axis Y=356.95/Z=147. Vendor 57×51, 34×34 pitch, Ø5.2 and 4.5 leaf thickness are recorded; 13.2 vs 12.8 overall thickness conflicts, so use 13.2 conservatively. Barrel/axis/knuckle geometry is provisional. `HingeBase0/1` are fixed leaves; legacy `HingePin0/1` are moving leaves, not separate purchased pins. Each pair makes one purchased hinge. Cover moves with `HingeSpacer0/1` and `HingeBacking0/1` in every renderer. Use `hinges.rotation` rather than deriving an axis from the cover bounds. Upper 2 mm spacer, 2 mm backing, Ø5.5 cover holes and rear Ø3×8 blind wood pilots are installation assumptions. Preserve 4 mm wood behind the pilots. Closed total depth is 363.2 mm, excluding unmodeled fasteners/cable; wood depth stays 350. Preserve A-P06/A-P07, append A-P08 and A-H03. User-reported max 3 N.m is not a tested torque rating; installation remains unreleased and the sampled 70° opening has no modeled stop.

Hinge symmetry and inlet clearance depend on three independent inputs: `hinges.center_x`, `ac_inlet.center_z`, and `power_transformer.center_y`. Changing one does not reposition the others. Rebuild both assemblies and the A-H02/A-H03 hole sheets after changing this layout; retain the wiring reservation and check transformer clearance. Do not move only a `HingePin` in the GUI. In the rear view, object suffix 0 at X=100 appears on the right.
