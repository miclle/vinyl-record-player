"""Run using FreeCAD's bundled Python: -m unittest discover -s tests -v."""
import contextlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
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
    def test_floating_deck_rear_clearance_survives_export_and_stock_sizing(self):
        for clearance, depth in [(2.0, 328.0), (7.0, 323.0)]:
            with self.subTest(clearance=clearance), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'cad').mkdir()
                params = json.loads((ROOT / 'cad/parameters.json').read_text())
                params['deck_rear_clearance'] = clearance
                (root / 'cad/parameters.json').write_text(json.dumps(params))
                (root / 'cad/selected-mechanism.json').write_bytes((ROOT / 'cad/selected-mechanism.json').read_bytes())
                with patch.object(build_model, 'ROOT', root):
                    doc, _, _ = build_model.deliver()
                    App.closeDocument(doc.Name)
                doc = App.openDocument(str(root / 'cad/lumi-selected-mechanism-fit.FCStd'))
                try:
                    deck = doc.FloatingDeck
                    bounds = deck.Shape.optimalBoundingBox(False)
                    self.assertAlmostEqual(deck.Shape.distToShape(doc.Back.Shape)[0], clearance)
                    self.assertAlmostEqual(bounds.YMin, 8.0)
                    self.assertAlmostEqual(bounds.YLength, depth)
                    self.assertAlmostEqual(bounds.XLength, 418.0)
                    self.assertAlmostEqual(bounds.ZLength, 6.0)
                    self.assertAlmostEqual(float(deck.StockWidth), depth)
                    for name in ['SideLeft', 'SideRight', 'Back', 'AcousticRoof',
                                 'PowerTransformer', 'Amplifier', 'ACInlet',
                                 'HingeBase0', 'HingeBase1', 'HingePin0', 'HingePin1']:
                        self.assertLess(deck.Shape.common(doc.getObject(name).Shape).Volume, 1e-6, name)
                finally:
                    App.closeDocument(doc.Name)

    def test_incompatible_model_replaces_success_report_and_closes_document(self):
        missing_neighbors = ['GrilleCloth', 'Fascia', 'LightChannel', 'LightDiffuser']
        cases = ['old_schema', 'missing_property', 'missing_snapshot', 'invalid_snapshot', 'Feet'] + missing_neighbors
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cad').mkdir()
            (root / 'tools').mkdir()
            shutil.copy2(ROOT / 'cad/parameters.json', root / 'cad/parameters.json')
            (root / 'cad/selected-mechanism.json').write_bytes((ROOT / 'cad/selected-mechanism.json').read_bytes())
            shutil.copy2(ROOT / 'tools/validate_model.py', root / 'tools/validate_model.py')
            shutil.copy2(ROOT / 'tools/ac_inlet.py', root / 'tools/ac_inlet.py')
            shutil.copy2(ROOT / 'tools/feet.py', root / 'tools/feet.py')
            shutil.copy2(ROOT / 'tools/fascia.py', root / 'tools/fascia.py')
            shutil.copy2(ROOT / 'tools/hinges.py', root / 'tools/hinges.py')
            shutil.copy2(ROOT / 'tools/assembly_pose.py', root / 'tools/assembly_pose.py')
            for case in cases:
                with self.subTest(case=case):
                    with patch.object(build_model, 'ROOT', root):
                        doc, params, _ = build_model.deliver()
                        datum = doc.getObject('GeometryDatums')
                        if case == 'old_schema':
                            for role in ['woofer', 'fullrange']:
                                params[role]['depth'] = params[role].pop('total_height')
                                params[role].pop('flange_thickness')
                            for name in ['Woofer', 'TweeterLeft', 'TweeterRight']:
                                doc.getObject(name).removeProperty('TotalHeight')
                                doc.getObject(name).removeProperty('FlangeThickness')
                            doc.removeObject('PowerTransformer')
                            datum.BuildParametersJSON = json.dumps(params)
                        elif case == 'missing_property':
                            doc.getObject('Woofer').removeProperty('TotalHeight')
                        elif case == 'missing_snapshot':
                            datum.removeProperty('BuildParametersJSON')
                        elif case in missing_neighbors or case == 'Feet':
                            doc.removeObject(case)
                            if case == 'Feet':
                                # Removing only the group must not hide the missing-group
                                # preflight behind a missing foot or mount error.
                                for prefix in ('Foot', 'FootMount'):
                                    for i in range(4):
                                        self.assertIsNotNone(doc.getObject(f'{prefix}{i}'))
                        else:
                            datum.BuildParametersJSON = '{invalid'
                        doc.recompute()
                        doc.save()
                        App.closeDocument(doc.Name)
                    report_path = root / 'cad/validation.json'
                    report_path.write_text('{"passed": true}')
                    opened_before = set(App.listDocuments())
                    try:
                        with patch.object(validate_model, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                            result = validate_model.validate()
                    finally:
                        opened_after = set(App.listDocuments())
                        for name in opened_after - opened_before:
                            App.closeDocument(name)
                    self.assertFalse(result['passed'])
                    self.assertEqual(json.loads(report_path.read_text()), result)
                    self.assertEqual(opened_after, opened_before)
                    self.assertTrue(result['errors'])
                    if case in missing_neighbors or case == 'Feet':
                        self.assertFalse(result['checks']['required_model_fields_present'])
                        self.assertIn(case, '\n'.join(result['errors']))
                    # Exercise the actual CLI exit path and overwrite a stale successful report.
                    report_path.write_text('{"passed": true}')
                    run = subprocess.run([sys.executable, str(root / 'tools/validate_model.py')],
                                         capture_output=True, text=True)
                    self.assertEqual(run.returncode, 1, run.stderr)
                    self.assertNotIn('Traceback', run.stderr)
                    self.assertFalse(json.loads(report_path.read_text())['passed'])

    def test_transformer_envelope_rejects_overlap_with_amplifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cad').mkdir()
            params = json.loads((ROOT / 'cad/parameters.json').read_text())
            params['power_transformer']['center_x'] = 360.0
            (root / 'cad/parameters.json').write_text(json.dumps(params))
            (root / 'cad/selected-mechanism.json').write_bytes((ROOT / 'cad/selected-mechanism.json').read_bytes())
            with patch.object(build_model, 'ROOT', root):
                doc, _, _ = build_model.deliver()
                App.closeDocument(doc.Name)
            with patch.object(validate_model, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                result = validate_model.validate()
            self.assertTrue(result['checks']['transformer_dimensions_match'])
            self.assertFalse(result['checks']['transformer_reservation_clear'])
            self.assertIn('Amplifier', [hit['part'] for hit in result['metrics']['transformer_reservation_collisions']])

    def test_saved_driver_height_is_checked_independently_of_metadata(self):
        import Part
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cad').mkdir()
            shutil.copy2(ROOT / 'cad/parameters.json', root / 'cad/parameters.json')
            (root / 'cad/selected-mechanism.json').write_bytes((ROOT / 'cad/selected-mechanism.json').read_bytes())
            with patch.object(build_model, 'ROOT', root):
                doc, params, _ = build_model.deliver()
                woofer = doc.getObject('Woofer')
                # Keep the parameter snapshot and properties intact, but corrupt geometry.
                woofer.Shape = Part.makeCylinder(params['woofer']['flange_diameter'] / 2,
                    params['woofer']['total_height'] + 1,
                    woofer.MountCentre - woofer.InwardAxis * float(woofer.FlangeThickness))
                doc.recompute()
                doc.save()
                App.closeDocument(doc.Name)
            with patch.object(validate_model, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                result = validate_model.validate()
            self.assertTrue(result['checks']['build_parameters_match'])
            self.assertTrue(result['checks']['driver_dimensions_match_parameters'])
            self.assertFalse(result['checks']['driver_geometry_matches_dimensions'])
            self.assertFalse(result['passed'])

    def test_changed_position_or_revision_rejects_stale_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cad').mkdir()
            shutil.copy2(ROOT / 'cad/parameters.json', root / 'cad/parameters.json')
            (root / 'cad/selected-mechanism.json').write_bytes((ROOT / 'cad/selected-mechanism.json').read_bytes())
            with patch.object(build_model, 'ROOT', root):
                doc, _, _ = build_model.deliver()
                App.closeDocument(doc.Name)
            with patch.object(validate_model, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(validate_model.validate()['passed'])
                original = json.loads((root / 'cad/parameters.json').read_text())
                for change in ['position', 'revision', 'amplifier_size']:
                    params = json.loads(json.dumps(original))
                    if change == 'position':
                        params['woofer']['center_x'] = 360.0
                    elif change == 'amplifier_size':
                        params['amplifier']['height'] += 1
                    else:
                        params['revision'] = 'different-build'
                    (root / 'cad/parameters.json').write_text(json.dumps(params))
                    (root / 'cad/selected-mechanism.json').write_bytes((ROOT / 'cad/selected-mechanism.json').read_bytes())
                    result = validate_model.validate()
                    with self.subTest(change=change):
                        self.assertFalse(result['passed'])


class AcousticLayoutTests(unittest.TestCase):
    def test_chamber_leak_and_blocked_port_are_detected_from_saved_solids(self):
        import Part
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'cad').mkdir()
            shutil.copy2(ROOT/'cad/parameters.json',root/'cad/parameters.json')
            shutil.copy2(ROOT/'cad/selected-mechanism.json',root/'cad/selected-mechanism.json')
            with patch.object(build_model,'ROOT',root):
                doc,p,_=build_model.deliver()
            try:
                divider=doc.getObject('AcousticDividerLeft')
                original=divider.Shape.copy()
                divider.Shape=divider.Shape.cut(Part.makeCylinder(6,20,App.Vector(125,110,70),App.Vector(1,0,0)))
                doc.recompute();doc.save()
                with patch.object(validate_model,'ROOT',root),contextlib.redirect_stdout(io.StringIO()):
                    result=validate_model._validate_document(doc,p)
                self.assertFalse(result['checks']['three_independent_enclosed_chambers'])
                divider.Shape=original
                port=doc.getObject('BassPort');spec=p['bass_port']
                port.Shape=port.Shape.fuse(Part.makeCylinder(spec['inner_diameter']/2,2,
                    App.Vector(spec['center_x'],p['depth']-spec['length']+2,spec['center_z']),App.Vector(0,1,0)))
                doc.recompute();doc.save()
                with patch.object(validate_model,'ROOT',root),contextlib.redirect_stdout(io.StringIO()):
                    result=validate_model._validate_document(doc,p)
                self.assertTrue(result['checks']['three_independent_enclosed_chambers'])
                self.assertFalse(result['checks']['bass_port_air_path_clear'])
                self.assertFalse(result['checks']['bass_port_dimensions_match'])
            finally:
                App.closeDocument(doc.Name)

    def test_shorter_satellite_chambers_remain_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'cad').mkdir()
            p=json.loads((ROOT/'cad/parameters.json').read_text())
            p['acoustic']['satellite_rear_y']=100.0
            (root/'cad/parameters.json').write_text(json.dumps(p))
            (root / 'cad/selected-mechanism.json').write_bytes((ROOT / 'cad/selected-mechanism.json').read_bytes())
            with patch.object(build_model,'ROOT',root):
                doc,_,_=build_model.deliver();App.closeDocument(doc.Name)
            with patch.object(validate_model,'ROOT',root),contextlib.redirect_stdout(io.StringIO()):
                result=validate_model.validate()
            self.assertTrue(result['passed'],result)
            chambers=result['metrics']['acoustics']['chambers']
            # The unchanged 117 x 90 mm chamber gains the 0.2 mm radial
            # panel clearance but loses the barrel/stud protruding above its floor.
            import math
            foot_delta = math.pi*((6.2**2-6**2)*12-6**2*2.5-4**2*6)/1e6
            for side in ('left','right'):
                self.assertAlmostEqual(chambers[side]['gross_after_recess_l'],
                                       0.64198162417+foot_delta,places=8)

    def test_electronics_in_chamber_reduce_net_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'cad').mkdir()
            original=json.loads((ROOT/'cad/parameters.json').read_text())
            net_volumes={}
            # The transformer reserves the full box above its mounting ears too.
            for case in ['baseline','amplifier','power_transformer']:
                p=json.loads(json.dumps(original))
                if case=='amplifier':p[case].update(x=180.0,y=55.0)
                if case=='power_transformer':p[case].update(center_x=224.3,center_y=110.0)
                (root/'cad/parameters.json').write_text(json.dumps(p))
                (root / 'cad/selected-mechanism.json').write_bytes((ROOT / 'cad/selected-mechanism.json').read_bytes())
                with patch.object(build_model,'ROOT',root):
                    doc,_,_=build_model.deliver();App.closeDocument(doc.Name)
                with patch.object(validate_model,'ROOT',root),contextlib.redirect_stdout(io.StringIO()):
                    result=validate_model.validate()
                self.assertTrue(result['passed'],result)
                net_volumes[case]=result['metrics']['acoustics']['chambers']['woofer']['conservative_net_l']
            self.assertAlmostEqual(net_volumes['baseline']-net_volumes['amplifier'],125*75*45/1e6,places=8)
            self.assertAlmostEqual(net_volumes['baseline']-net_volumes['power_transformer'],88*55*50/1e6,places=8)

    def test_replaceable_port_lengths_fit_and_displace_chamber_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'cad').mkdir()
            p=json.loads((ROOT/'cad/parameters.json').read_text())
            volumes=[]
            for length in p['bass_port']['trial_lengths']:
                with self.subTest(length=length):
                    p['bass_port']['length']=length
                    (root/'cad/parameters.json').write_text(json.dumps(p))
                    (root / 'cad/selected-mechanism.json').write_bytes((ROOT / 'cad/selected-mechanism.json').read_bytes())
                    with patch.object(build_model,'ROOT',root):
                        doc,_,_=build_model.deliver();App.closeDocument(doc.Name)
                    with patch.object(validate_model,'ROOT',root),contextlib.redirect_stdout(io.StringIO()):
                        result=validate_model.validate()
                    self.assertTrue(result['passed'],result)
                    chambers=result['metrics']['acoustics']['chambers']
                    self.assertGreater(chambers['woofer']['conservative_net_l'],3.9)
                    self.assertGreater(chambers['left']['conservative_net_l'],1.1)
                    volumes.append(chambers['woofer']['conservative_net_l'])
            self.assertGreater(volumes[0],volumes[1])
            self.assertGreater(volumes[1],volumes[2])


class MacroReloadTests(unittest.TestCase):
    def test_macro_reads_new_source_for_all_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'tools'
            root.mkdir()
            (root.parent/'cad').mkdir()
            (root.parent/'cad/mechanism-fit-report.json').write_text('{}')
            macro = root / 'build.FCMacro'
            shutil.copy2(ROOT / 'tools/build.FCMacro', macro)
            def write_sources(version):
                (root / 'ac_inlet.py').write_text(f'value = {version}\n')
                (root / 'feet.py').write_text(f'value = {version}\n')
                (root / 'fascia.py').write_text(f'value = {version}\n')
                (root / 'hinges.py').write_text(f'value = {version}\n')
                (root / 'build_model.py').write_text(f'from types import SimpleNamespace\nclass Doc:\n    StudyBasis = SimpleNamespace(ConfigurationJSON="{{}}")\n    def save(self): pass\ndef deliver():\n    return Doc(), {{"cover_angle_open":70}}, {version}\n')
                (root / 'mechanism_study.py').write_text(f'def render_study(*a): pass\ndef save_report(*a): pass\nvalue={version}\n')
                (root / 'assembly_pose.py').write_text('def set_cover_angle(*a): pass\n')
                (root / 'render_views.py').write_text(f'def render(*args):\n    return {version}\n')
                (root / 'dimension_sheet.py').write_text(f'def create(*args):\n    return {version}\n')
            saved_path = sys.path[:]
            try:
                gui=types.ModuleType('FreeCADGui')
                gui.activeDocument=lambda: types.SimpleNamespace(activeView=lambda: types.SimpleNamespace(fitAll=lambda: None))
                with patch.dict(sys.modules, {'FreeCADGui': gui}):
                    for name in ['ac_inlet', 'feet', 'fascia', 'hinges', 'build_model', 'render_views', 'dimension_sheet', 'mechanism_study', 'assembly_pose']:
                        sys.modules.pop(name, None)
                    env = {'__file__': str(macro), '__name__': '__main__'}
                    write_sources(1)
                    exec(compile(macro.read_bytes(), str(macro), 'exec'), env)
                    write_sources(2)  # Same size, immediate edit: also exercises stale bytecode.
                    exec(compile(macro.read_bytes(), str(macro), 'exec'), env)
                    self.assertEqual(env['groups'], 2)
                    self.assertEqual(env['mechanism_study'].value, 2)
                    self.assertEqual(env['render_views'].render(), 2)
                    self.assertEqual(env['dimension_sheet'].create(), 2)
                    self.assertIsNotNone(env.get('ac_inlet'))
                    self.assertEqual(env['ac_inlet'].value, 2)
                    self.assertEqual(env['hinges'].value, 2)
            finally:
                sys.path[:] = saved_path

    def test_toggle_macro_reads_current_pose_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'tools'
            root.mkdir()
            macro = root / 'toggle-cover.FCMacro'
            shutil.copy2(ROOT / 'tools/toggle-cover.FCMacro', macro)
            state = types.SimpleNamespace(CoverAngle=0)
            doc = types.SimpleNamespace(
                AssemblyState=state,
                GeometryDatums=types.SimpleNamespace(BuildParametersJSON='{"cover_angle_open": 70}'),
            )
            doc.getObject = lambda name: state if name == 'AssemblyState' else None
            app = types.ModuleType('FreeCAD')
            app.ActiveDocument = doc
            gui = types.ModuleType('FreeCADGui')
            gui.activeDocument = lambda: types.SimpleNamespace(
                activeView=lambda: types.SimpleNamespace(fitAll=lambda: None))
            gui.updateGui = lambda: None

            def write_sources(version):
                (root / 'hinges.py').write_text(f'value = {version}\n')
                (root / 'assembly_pose.py').write_text(
                    'from hinges import value\n'
                    'def set_cover_angle(doc, parameters, angle):\n'
                    '    doc.loaded_version = value\n'
                    '    doc.AssemblyState.CoverAngle = angle\n')

            saved_path = sys.path[:]
            try:
                with patch.dict(sys.modules, {'FreeCAD': app, 'FreeCADGui': gui}):
                    write_sources(1)
                    exec(compile(macro.read_bytes(), str(macro), 'exec'),
                         {'__file__': str(macro), '__name__': '__main__'})
                    self.assertEqual(doc.loaded_version, 1)
                    write_sources(2)
                    exec(compile(macro.read_bytes(), str(macro), 'exec'),
                         {'__file__': str(macro), '__name__': '__main__'})
                    self.assertEqual(doc.loaded_version, 2)
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
            cfg=json.loads((ROOT/'cad/selected-mechanism.json').read_text())
            cfg.update(platter_diameter=310,platter_center_x=params['platter_x'],platter_center_y=params['platter_y'])
            doc = types.SimpleNamespace(getObject=lambda name: group, StudyBasis=types.SimpleNamespace(ConfigurationJSON=json.dumps(cfg)))
            svg = module.create(doc, params).read_text()
            for expected in ['Ø310', '弯臂机芯尺寸待确认', '后倾 20°', '木壳厚 14', '* 216', 'v0.3-review']:
                with self.subTest(expected=expected):
                    self.assertIn(expected, svg)
            line = re.search(r'd="M([\d.]+),([\d.]+) H([\d.]+)"/><text[^>]*>Ø310', svg)
            self.assertIsNotNone(line)
            scale = 1.15
            start = 80 + (cfg['platter_center_x'] - cfg['platter_diameter'] / 2) * scale
            expected_values = [start,
                               510 - cfg['platter_center_y'] * scale,
                               start + cfg['platter_diameter'] * scale]
            for actual, expected in zip(line.groups(), expected_values):
                self.assertAlmostEqual(float(actual), expected)


if __name__ == '__main__':
    unittest.main()
