"""Verify measured mechanism diagnostics in the generated main model."""
import csv
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import FreeCAD as App
import Part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_model
import mechanism_study
from model_sections import section_objects


class MechanismStudyTests(unittest.TestCase):
    def copy_inputs(self, root):
        (root / 'cad').mkdir()
        for name in ['parameters.json', 'mechanism.json']:
            shutil.copy2(ROOT / 'cad' / name, root / 'cad' / name)

    def test_reopened_output_blocks_rebuild_without_changing_files_or_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.copy_inputs(root)
            with patch.object(build_model, 'ROOT', root):
                doc, _, _ = build_model.deliver()
                App.closeDocument(doc.Name)
                output = root / 'cad/record-player.FCStd'
                alias = root / 'reopened-study.FCStd'
                alias.symlink_to(output)
                for opened_path in [output, alias]:
                    with self.subTest(opened_path=opened_path.name):
                        reopened = App.openDocument(str(opened_path))
                        self.assertNotEqual(reopened.Name, 'RecordPlayerAssembly')
                        reopened.KitPlatter.Label = 'unsaved user edit'
                        documents_before = set(App.listDocuments())
                        files_before = {p.name: p.read_bytes() for p in (root / 'cad').iterdir()}
                        try:
                            with self.assertRaisesRegex(RuntimeError, 'close'):
                                build_model.deliver()
                            self.assertEqual(set(App.listDocuments()), documents_before)
                            self.assertEqual(reopened.KitPlatter.Label, 'unsaved user edit')
                            self.assertEqual(
                                {p.name: p.read_bytes() for p in (root / 'cad').iterdir()}, files_before)
                        finally:
                            for name in set(App.listDocuments()) - documents_before:
                                App.closeDocument(name)
                            App.closeDocument(reopened.Name)

    def test_saved_measurements_support_positions_and_two_height_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.copy_inputs(root)
            with patch.object(build_model, 'ROOT', root):
                doc, _, _ = build_model.deliver()
            report = json.loads((root / 'cad/mechanism-fit-report.json').read_text())
            App.closeDocument(doc.Name)
            saved = App.openDocument(str(root / 'cad/record-player.FCStd'))
            try:
                cfg = json.loads((root / 'cad/mechanism.json').read_text())
                self.assertTrue(all(report['geometry_checks'].values()))
                self.assertEqual(json.loads(saved.StudyBasis.ConfigurationJSON), cfg)
                b = saved.KitPlatter.Shape.optimalBoundingBox(False)
                self.assertAlmostEqual(b.XLength, 280)
                self.assertAlmostEqual(b.YLength, 280)
                self.assertAlmostEqual(b.ZLength, 11)
                arm = saved.KitCurvedArm.Shape.optimalBoundingBox(False)
                headshell = saved.KitHeadshell.Shape
                head_bounds = headshell.optimalBoundingBox(False)
                base_bounds = saved.KitBase.Shape.optimalBoundingBox(False)
                deck_bounds = saved.FloatingDeck.Shape.optimalBoundingBox(False)
                self.assertGreater(arm.XLength, 2 * cfg['appearance_assumptions']['arm_bend_radius'])
                self.assertGreater(head_bounds.XLength, cfg['appearance_assumptions']['headshell_width'])
                self.assertGreater(head_bounds.YLength, cfg['appearance_assumptions']['headshell_length'])
                self.assertLessEqual(head_bounds.XMax, base_bounds.XMax)
                self.assertAlmostEqual(base_bounds.XMin-deck_bounds.XMin,
                                       deck_bounds.XMax-base_bounds.XMax, delta=1)
                self.assertEqual(len(headshell.Solids), 1)
                self.assertGreaterEqual(len(headshell.Faces), 20)  # Connector, two slots and top pads.
                arm_parts = [saved.getObject(name).Shape.optimalBoundingBox(False) for name in
                             ['KitCurvedArm', 'KitCounterweight', 'KitHeadshell', 'KitCartridge']]
                self.assertAlmostEqual(max(b.YMax for b in arm_parts) - min(b.YMin for b in arm_parts),
                                       cfg['arm_total_length'], places=5)
                springs = saved.KitBase.Shape.Solids[1:]
                self.assertEqual(len(springs), 3)
                expected = mechanism_study.measurement_datums(cfg, 150)['spring_centers_xy_mm']
                for spring, (x, y) in zip(springs, expected):
                    bounds = spring.optimalBoundingBox(False)
                    self.assertAlmostEqual(bounds.Center.x, x, places=5)
                    self.assertAlmostEqual(bounds.Center.y, y, places=5)
                    self.assertAlmostEqual(bounds.ZMin, 146.5)
                    self.assertAlmostEqual(bounds.ZLength, 10.5)
                low = saved.UnderbodyReservation.Shape.optimalBoundingBox(False).ZMin
                high = max(o.Shape.optimalBoundingBox(False).ZMax for o in section_objects(saved, 'SelectedKit'))
                self.assertAlmostEqual(low, 117)
                self.assertAlmostEqual(high-low, 85)
                self.assertLess(saved.UnderbodyReservation.Shape.Volume, 355*280*29.5)
                fit = report['fit']
                p = json.loads((root / 'cad/parameters.json').read_text())
                self.assertFalse(fit['installation_released'])
                self.assertFalse(fit['underbody_coverage_complete'])
                states = fit['spring_states']
                self.assertEqual([s['motor_depth_below_support_mm'] for s in states], [24.5, 29.5])
                roof_depth = (p['cabinet_top'] - p['acoustic']['roof_bottom_z']
                              - p['acoustic']['roof_thickness'])
                self.assertEqual([s['roof_depth_deficit_mm'] for s in states],
                                 [24.5-roof_depth, 29.5-roof_depth])
                self.assertAlmostEqual(states[0]['upper_vertical_lid_gap_mm'], 0.7)
                self.assertAlmostEqual(states[1]['upper_vertical_lid_gap_mm'], 5.7)
                for state in states:
                    self.assertEqual(state['cover_sweep_sample_count'], 71)
                    self.assertEqual(state['cover_sweep_collisions'], [])
                    self.assertIn('AcousticRoof', [hit['part'] for hit in state['local_underbody_overlaps']])
                self.assertAlmostEqual(fit['display_cover_clearance_mm'], 5.7)
                self.assertAlmostEqual(fit['illustrative_cover_clearance_mm'], 0.7)
                self.assertTrue(all(o.IsReference for o in section_objects(saved, 'Mechanism')))
                self.assertFalse(any(o.TypeId == 'App::DocumentObjectGroup' for o in saved.Objects))
                self.assertTrue(all(o in saved.RootObjects for o in saved.Objects
                                    if o.TypeId == 'Part::Feature'))
                self.assertEqual(list((root / 'cad').glob('*.FCStd')),
                                 [root / 'cad/record-player.FCStd'])
                self.assertEqual(report['model_sha256'], hashlib.sha256(
                    (root / 'cad/record-player.FCStd').read_bytes()).hexdigest())
                with (root / 'cad/parts.csv').open(encoding='utf-8-sig') as f:
                    ids = {row['ID'] for row in csv.DictReader(f)}
                physical = [o for o in saved.Objects if o.TypeId == 'Part::Feature'
                            and not getattr(o, 'IsReference', False)
                            and not getattr(o, 'IsDiagnostic', False)]
                self.assertEqual(ids, {o.Name for o in physical})
                exported = Part.read(str(root / 'cad/record-player.step'))
                self.assertEqual(len(exported.Solids), sum(len(o.Shape.Solids) for o in physical))
                self.assertLess(abs(exported.Volume-sum(o.Shape.Volume for o in physical))/exported.Volume,
                                1e-7)
            finally:
                App.closeDocument(saved.Name)

    def test_free_spring_collision_fails_build_despite_clear_display_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.copy_inputs(root)
            path = root / 'cad/mechanism.json'
            cfg = json.loads(path.read_text())
            cfg['spring_free_height'] = 16.5
            path.write_text(json.dumps(cfg))
            try:
                with patch.object(build_model, 'ROOT', root):
                    with self.assertRaisesRegex(RuntimeError, 'geometry/export validation failed'):
                        build_model.deliver()
            finally:
                failed = App.getDocument('RecordPlayerAssembly')
                if failed is not None:
                    App.closeDocument(failed.Name)
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
        cfg = json.loads((ROOT / 'cad/mechanism.json').read_text())
        cfg['spring_radius'] = 100
        d = mechanism_study.measurement_datums(cfg, 150, 2)
        self.assertAlmostEqual(d['spring_centers_xy_mm'][0][0], cfg['platter_center_x'] + 50)
        self.assertAlmostEqual(d['lowest_z_mm'], 123.5)
        cfg['total_height'] += 1
        with self.assertRaisesRegex(ValueError, 'height chain'):
            mechanism_study.measurement_datums(cfg, 150)
        cfg['total_height'] -= 1
        with self.assertRaisesRegex(ValueError, 'compression'):
            mechanism_study.measurement_datums(cfg, 150, 16)

    def test_headshell_details_follow_nondefault_length_and_width(self):
        cfg = json.loads((ROOT / 'cad/mechanism.json').read_text())
        appearance = cfg['appearance_assumptions']
        for length, width in [(27, 22), (52, 14)]:
            with self.subTest(length=length, width=width):
                custom = dict(appearance, headshell_length=length, headshell_width=width)
                shape, _, _ = mechanism_study.headshell_shape(App.Vector(),
                                                               custom['headshell_yaw_degrees'],
                                                               custom, 0)
                self.assertTrue(shape.isValid())
                self.assertEqual(len(shape.Solids), 1)


if __name__ == '__main__':
    unittest.main()
