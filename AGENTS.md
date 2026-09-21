# Repository Guidelines

## Project Structure & Module Organization

FreeCAD model of a turntable with one downward-facing woofer and two front tweeters.

- `tools/build_model.py`: geometry generation and CAD export.
- `tools/build.FCMacro`: GUI entry point; invokes generation, rendering, and dimension-sheet creation.
- `tools/render_views.py` and `tools/dimension_sheet.py`: viewport previews and projected drawings.
- `tools/validate_model.py`: geometry and STEP validation; `tests/test_regressions.py`: regression tests.
- `cad/`: `parameters.json`, current `lumi-three-driver.FCStd` / `.step`, parts list, and validation report. `lumi-dual-driver.*` files are historical.
- `previews/`: generated PNG and SVG assets.
- `docs/design-basis.md`: sources, assumptions, and manufacturing limitations. `references/hym-lumi/` contains attributed reference images.

## Build, Test, and Development Commands

Use FreeCAD 1.1.1. Run commands from the repository root.

```sh
open -a FreeCAD --args "$PWD/tools/build.FCMacro"
```

On macOS, this starts generation when FreeCAD is closed. Otherwise, execute the macro through FreeCAD's Macro dialog. Save manual edits separately and close `LumiThreeDriver` before rebuilding. The macro does not run validation; run it separately afterward.

```sh
PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
  /Applications/FreeCAD.app/Contents/Resources/bin/python tools/validate_model.py
git diff --check
```

Validation writes `cad/validation.json` and exits nonzero on failure. Substitute `tools/build_model.py` to regenerate CAD and the parts list without GUI colors, previews, or a refreshed validation report.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions and JSON keys, and stable descriptive CAD object IDs such as `TweeterLeft`. Preserve Chinese user-facing labels. All geometry uses millimetres; suffix reported measurements with `_mm` where appropriate. Resolve paths from script locations. No formatter or linter is configured.

## Testing Guidelines

Use FreeCAD’s Python to run `-m unittest discover -s tests -v`. Tests use temporary directories. Validation uses FreeCAD and Open CASCADE; no coverage threshold is configured. Add descriptive boolean checks for changed dimensions, mounting clearances, or export behavior. After geometry changes, regenerate deliverables, run validation, and visually inspect affected previews. Export leaf `Part::Feature` objects only to avoid duplicated group geometry.

## Commit & Pull Request Guidelines

No established commit convention exists. Prefer concise imperative messages, optionally prefixed with `feat:`, `fix:`, or `docs:`. PRs should explain dimension changes, assumptions, validation results, and relevant issues, with before/after previews for geometry changes. Include regenerated artifacts alongside their source changes; exclude ignored backups and logs.

## Modeling Boundaries

Edit `cad/parameters.json` and rebuild: saved `Part::Feature` solids do not update automatically. Validation rejects mismatched or missing parameter snapshots. Distinguish estimates from measured dimensions. Passing geometry checks does not establish acoustic performance or manufacturing readiness. Reference photos retain their owners' copyright; the repository license does not cover them.
