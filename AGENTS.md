# Repository Guidelines

## Project Structure & Module Organization

FreeCAD concept model of a turntable with one downward-facing woofer, two front tweeters, a shared transformer, and an amplifier including its heatsink. The selected curved-arm mechanism has a separate fit-study assembly; installation is not released.

- `tools/build_model.py`: geometry generation and CAD export.
- `tools/build.FCMacro`: GUI entry point; invokes generation, rendering, and dimension-sheet creation.
- `tools/render_views.py` and `tools/dimension_sheet.py`: viewport previews and projected drawings.
- `tools/validate_model.py`: baseline geometry and STEP validation; `tests/test_regressions.py`: regression tests.
- `tools/mechanism_study.py` and `tools/mechanism-study.FCMacro`: selected-mechanism assembly, fit report, and GUI previews; `tests/test_mechanism_study.py`: fit-study regression tests.
- `cad/parameters.json`: cabinet, drivers, transformer, and amplifier inputs; `lumi-three-driver.FCStd` / `.step`, `parts.csv`, and `validation.json` are baseline outputs.
- `cad/selected-mechanism.json`: mechanism assumptions; `lumi-selected-mechanism-fit.FCStd` / `.step` and `mechanism-fit-report.json` are fit-study outputs. The study reads the saved baseline FCStd. `lumi-dual-driver.*` files are historical.
- `previews/`: generated PNG and SVG assets.
- `docs/design-basis.md`: dimension sources and manufacturing limitations; `docs/selected-mechanism.md`: fit-study assumptions, rebuild sequence, and remaining installation work. Reference images are under `references/`.

## Build, Test, and Development Commands

Use FreeCAD 1.1.1. Run commands from the repository root.

```sh
open -a FreeCAD --args "$PWD/tools/build.FCMacro"
```

On macOS, this starts generation when FreeCAD is closed. Otherwise, execute the macro through FreeCAD's Macro dialog. Save manual edits separately and close the baseline file before rebuilding, including reopened files whose document names differ from `LumiThreeDriver`; the baseline generator only guards that document name. The macro does not run validation; run it separately afterward.

```sh
PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
  /Applications/FreeCAD.app/Contents/Resources/bin/python tools/validate_model.py
git diff --check
```

Validation checks the parameter snapshot and required installation fields before geometry. A failed preflight writes `passed: false` and `errors` to `cad/validation.json`, replacing any previous success report, then exits nonzero. The validator closes the document it opened. Substitute `tools/build_model.py` to regenerate CAD and the parts list without GUI colors, previews, or a refreshed validation report.

After baseline changes, rebuild and validate the baseline first, then execute `tools/mechanism-study.FCMacro` in FreeCAD. Save manual edits separately and close the study output before rebuilding; the study guards both document name and resolved output path. Its macro regenerates the study, report, and two previews, while `tools/mechanism_study.py` alone generates no GUI previews. The study report records the baseline SHA-256. Do not delete the baseline FCStd while this dependency remains.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions and JSON keys, and stable descriptive CAD object IDs such as `TweeterLeft`. Preserve Chinese user-facing labels. All geometry uses millimetres; suffix reported measurements with `_mm` where appropriate. Resolve paths from script locations. No formatter or linter is configured.

## Testing Guidelines

Use FreeCAD’s Python to run `-m unittest discover -s tests -v`. Tests use temporary directories. Validation uses FreeCAD and Open CASCADE; no coverage threshold is configured. Add descriptive boolean checks for changed dimensions, mounting clearances, or export behavior. After geometry changes, regenerate deliverables, run validation, and visually inspect affected previews. Export leaf `Part::Feature` objects only to avoid duplicated group geometry.

## Commit & Pull Request Guidelines

No established commit convention exists. Prefer concise imperative messages, optionally prefixed with `feat:`, `fix:`, or `docs:`. PRs should explain dimension changes, assumptions, validation results, and relevant issues, with before/after previews for geometry changes. Include regenerated artifacts alongside their source changes; exclude ignored backups and logs.

## Modeling Boundaries

Edit `cad/parameters.json` and rebuild: saved `Part::Feature` solids do not update automatically. Validation rejects mismatched or missing parameter snapshots. Driver `total_height` includes `flange_thickness`; inward depth is their difference. Amplifier dimensions already include the heatsink. Transformer ear width/thickness, speaker cutouts, mounting holes, and amplifier floor clearance remain assumptions. Distinguish user-provided dimensions from estimates. Passing geometry checks does not establish acoustic performance or manufacturing readiness. Reference photos retain their owners' copyright; the repository license does not cover them.
