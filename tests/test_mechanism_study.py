"""Verify candidate-envelope diagnostics without modifying delivered models."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import mechanism_study


class MechanismStudyTests(unittest.TestCase):
    def test_reopened_output_blocks_rebuild_without_changing_files_or_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cad').mkdir()
            for name in ['lumi-three-driver.FCStd', 'selected-mechanism.json', 'lumi-selected-mechanism-fit.FCStd']:
                shutil.copy2(ROOT / 'cad' / name, root / 'cad' / name)
            with patch.object(mechanism_study, 'ROOT', root):
                output = root / 'cad/lumi-selected-mechanism-fit.FCStd'
                alias = root / 'reopened-study.FCStd'
                alias.symlink_to(output)
                for opened_path in [output, alias]:
                    with self.subTest(opened_path=opened_path.name):
                        reopened = App.openDocument(str(opened_path))
                        self.assertNotEqual(reopened.Name, 'LumiMechanismStudy')
                        reopened.KitPlatter.Label = 'unsaved user edit'
                        documents_before = set(App.listDocuments())
                        files_before = {p.name: p.read_bytes() for p in (root / 'cad').iterdir()}
                        try:
                            with self.assertRaisesRegex(RuntimeError, 'close'):
                                mechanism_study.build_study()
                            self.assertEqual(set(App.listDocuments()), documents_before)
                            self.assertEqual(reopened.KitPlatter.Label, 'unsaved user edit')
                            self.assertEqual(
                                {p.name: p.read_bytes() for p in (root / 'cad').iterdir()},
                                files_before,
                            )
                        finally:
                            for name in set(App.listDocuments()) - documents_before:
                                App.closeDocument(name)
                            App.closeDocument(reopened.Name)

    def test_saved_measurements_support_positions_and_two_height_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cad').mkdir()
            for name in ['lumi-three-driver.FCStd', 'selected-mechanism.json']:
                shutil.copy2(ROOT / 'cad' / name, root / 'cad' / name)
            with patch.object(mechanism_study, 'ROOT', root):
                doc, cfg, report = mechanism_study.build_study()
                App.closeDocument(doc.Name)
                saved = App.openDocument(str(root / 'cad/lumi-selected-mechanism-fit.FCStd'))
                try:
                    self.assertTrue(all(report['geometry_checks'].values()))
                    self.assertEqual(json.loads(saved.StudyBasis.ConfigurationJSON), cfg)
                    b = saved.KitPlatter.Shape.optimalBoundingBox(False)
                    self.assertAlmostEqual(b.XLength, 280)
                    self.assertAlmostEqual(b.YLength, 280)
                    self.assertAlmostEqual(b.ZLength, 11)
                    # Read the three saved spring sleeves, not just computed metadata.
                    springs = saved.KitBase.Shape.Solids[1:]
                    self.assertEqual(len(springs), 3)
                    expected = [(231, 267.262794), (271.262794, 117), (80.737206, 117)]
                    for spring, (x, y) in zip(springs, expected):
                        bounds = spring.optimalBoundingBox(False)
                        self.assertAlmostEqual(bounds.Center.x, x, places=5)
                        self.assertAlmostEqual(bounds.Center.y, y, places=5)
                        self.assertAlmostEqual(bounds.ZMin, 146.5)
                        self.assertAlmostEqual(bounds.ZLength, 10.5)
                    low = saved.UnderbodyReservation.Shape.optimalBoundingBox(False).ZMin
                    high = max(o.Shape.optimalBoundingBox(False).ZMax for o in saved.SelectedKit.Group)
                    self.assertAlmostEqual(low, 117)
                    self.assertAlmostEqual(high-low, 85)
                    self.assertLess(saved.UnderbodyReservation.Shape.Volume, 355*280*29.5)
                    fit = report['fit']
                    self.assertFalse(fit['installation_released'])
                    self.assertFalse(fit['underbody_coverage_complete'])
                    states = fit['spring_states']
                    self.assertEqual([s['motor_depth_below_support_mm'] for s in states], [24.5, 29.5])
                    self.assertEqual([s['roof_depth_deficit_mm'] for s in states], [10.5, 15.5])
                    self.assertAlmostEqual(states[0]['upper_vertical_lid_gap_mm'], 0.7)
                    self.assertAlmostEqual(states[1]['upper_vertical_lid_gap_mm'], 5.7)
                    for state in states:
                        self.assertEqual(state['cover_sweep_sample_count'], 71)
                        self.assertEqual(state['cover_sweep_collisions'], [])
                        self.assertIn('AcousticRoof', [hit['part'] for hit in state['local_underbody_overlaps']])
                    self.assertAlmostEqual(fit['display_cover_clearance_mm'], 5.7)
                    self.assertAlmostEqual(fit['illustrative_cover_clearance_mm'], 0.7)
                    self.assertIsNone(saved.getObject('Mechanism'))
                finally:
                    App.closeDocument(saved.Name)

    def test_free_spring_collision_fails_cli_despite_clear_display_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cad').mkdir()
            (root / 'tools').mkdir()
            for name in ['lumi-three-driver.FCStd', 'selected-mechanism.json']:
                shutil.copy2(ROOT / 'cad' / name, root / 'cad' / name)
            script = root / 'tools/mechanism_study.py'
            shutil.copy2(ROOT / 'tools/mechanism_study.py', script)
            path = root / 'cad/selected-mechanism.json'
            cfg = json.loads(path.read_text())
            cfg['spring_free_height'] = 16.5
            path.write_text(json.dumps(cfg))
            result = subprocess.run(
                [sys.executable, '-c',
                 'import sys,runpy; sys.path.insert(0,sys.argv[1]); runpy.run_path(sys.argv[2],run_name="__main__")',
                 str(ROOT / 'tools'), str(script)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('geometry/export validation failed', result.stderr)
            report = json.loads((root / 'cad/mechanism-fit-report.json').read_text())
            fit = report['fit']
            self.assertTrue(fit['display_closed_cover_clear'])
            self.assertGreater(fit['display_cover_clearance_mm'], 0)
            self.assertGreater(fit['spring_states'][0]['closed_cover_overlap_mm3'], 260)
            self.assertFalse(fit['illustrative_closed_cover_clear'])
            self.assertEqual(fit['illustrative_cover_clearance_mm'], 0)
            self.assertFalse(report['geometry_checks']['spring_endpoints_closed_cover_clear'])
            self.assertFalse(report['geometry_checks']['spring_endpoints_cover_sweep_clear'])
            self.assertTrue(report['geometry_checks']['hinge_cover_assembly_sweep_clear'])

    def test_datum_change_and_invalid_height_chain(self):
        cfg = json.loads((ROOT / 'cad/selected-mechanism.json').read_text())
        cfg['spring_radius'] = 100
        d = mechanism_study.measurement_datums(cfg, 150, 2)
        self.assertAlmostEqual(d['spring_centers_xy_mm'][0][0], 226)
        self.assertAlmostEqual(d['lowest_z_mm'], 123.5)
        cfg['total_height'] += 1
        with self.assertRaisesRegex(ValueError, 'height chain'):
            mechanism_study.measurement_datums(cfg, 150)
        cfg['total_height'] -= 1
        with self.assertRaisesRegex(ValueError, 'compression'):
            mechanism_study.measurement_datums(cfg, 150, 16)


if __name__ == '__main__':
    unittest.main()
