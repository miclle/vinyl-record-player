"""Run using FreeCAD's bundled Python: -m unittest discover -s tests -v."""
import contextlib
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_model
import validate_model


class ParameterValidationTests(unittest.TestCase):
    def test_changed_position_or_revision_rejects_stale_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cad').mkdir()
            shutil.copy2(ROOT / 'cad/parameters.json', root / 'cad/parameters.json')
            with patch.object(build_model, 'ROOT', root):
                doc, _, _ = build_model.deliver()
                App.closeDocument(doc.Name)
            with patch.object(validate_model, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(validate_model.validate()['passed'])
                original = json.loads((root / 'cad/parameters.json').read_text())
                for change in ['position', 'revision']:
                    params = json.loads(json.dumps(original))
                    if change == 'position':
                        params['woofer']['center_x'] = 300.0
                    else:
                        params['revision'] = 'different-build'
                    (root / 'cad/parameters.json').write_text(json.dumps(params))
                    result = validate_model.validate()
                    with self.subTest(change=change):
                        self.assertFalse(result['passed'])


class MacroReloadTests(unittest.TestCase):
    def test_macro_reads_new_source_for_all_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            macro = root / 'build.FCMacro'
            shutil.copy2(ROOT / 'tools/build.FCMacro', macro)
            def write_sources(version):
                (root / 'build_model.py').write_text(f'def deliver():\n    return {version}, {version}, {version}\n')
                (root / 'render_views.py').write_text(f'def render(*args):\n    return {version}\n')
                (root / 'dimension_sheet.py').write_text(f'def create(*args):\n    return {version}\n')
            saved_path = sys.path[:]
            try:
                with patch.dict(sys.modules, {'FreeCADGui': types.ModuleType('FreeCADGui')}):
                    for name in ['build_model', 'render_views', 'dimension_sheet']:
                        sys.modules.pop(name, None)
                    env = {'__file__': str(macro), '__name__': '__main__'}
                    write_sources(1)
                    exec(compile(macro.read_bytes(), str(macro), 'exec'), env)
                    write_sources(2)  # Same size, immediate edit: also exercises stale bytecode.
                    exec(compile(macro.read_bytes(), str(macro), 'exec'), env)
                    self.assertEqual(env['doc'], 2)
                    self.assertEqual(env['render_views'].render(), 2)
                    self.assertEqual(env['dimension_sheet'].create(), 2)
            finally:
                sys.path[:] = saved_path


class DrawingAnnotationTests(unittest.TestCase):
    def test_annotations_follow_nondefault_parameters(self):
        # Isolate SVG annotation generation from the GUI projection/rasterizer.
        fake_techdraw = types.ModuleType('TechDraw')
        fake_techdraw.projectToSVG = lambda *args: '<g/>'
        fake_qt = types.ModuleType('PySide')
        class DummyImage:
            Format_ARGB32 = 0
            def __init__(self, *args): pass
            def fill(self, *args): pass
            def save(self, *args): pass
        class DummyPainter:
            def __init__(self, *args): pass
            def end(self): pass
        fake_qt.QtGui = types.SimpleNamespace(QImage=DummyImage, QPainter=DummyPainter)
        fake_qt.QtCore = types.SimpleNamespace(Qt=types.SimpleNamespace(white=0))
        fake_qt.QtSvg = types.SimpleNamespace(QSvgRenderer=lambda *args: types.SimpleNamespace(render=lambda *a: None))
        import Part
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {'TechDraw': fake_techdraw, 'PySide': fake_qt}):
            root = Path(tmp)
            (root / 'previews').mkdir()
            (root / 'previews/open.png').write_bytes(b'preview')
            spec = importlib.util.spec_from_file_location('drawing_under_test', ROOT / 'tools/dimension_sheet.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.ROOT = root
            params = json.loads((ROOT / 'cad/parameters.json').read_text())
            params.update(platter_diameter=310, pivot_distance=202, arm_effective_length=220,
                          front_angle=70, wall=14, closed_height=216, revision='v0.3-review')
            group = types.SimpleNamespace(Group=[types.SimpleNamespace(Shape=Part.makeBox(1, 1, 1))])
            doc = types.SimpleNamespace(getObject=lambda name: group)
            svg = module.create(doc, params).read_text()
            for expected in ['Ø310', '轴距 202', '有效臂长 220', '后倾 20°', '木壳厚 14', '* 216', 'v0.3-review']:
                with self.subTest(expected=expected):
                    self.assertIn(expected, svg)
            line = re.search(r'd="M([\d.]+),([\d.]+) H([\d.]+)"/><text[^>]*>Ø310', svg)
            self.assertIsNotNone(line)
            for actual, expected in zip(line.groups(), [104.15, 312.2, 460.65]):
                self.assertAlmostEqual(float(actual), expected)


if __name__ == '__main__':
    unittest.main()
