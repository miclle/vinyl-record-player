"""Verify candidate-envelope diagnostics without modifying delivered models."""
import json
import shutil
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
            for name in ['lumi-three-driver.FCStd', 'selected-mechanism.json']:
                shutil.copy2(ROOT / 'cad' / name, root / 'cad' / name)
            with patch.object(mechanism_study, 'ROOT', root):
                doc, _, _ = mechanism_study.build_study()
                App.closeDocument(doc.Name)
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

    def test_assumed_depth_changes_roof_conflict_without_releasing_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cad').mkdir()
            for name in ['lumi-three-driver.FCStd', 'selected-mechanism.json']:
                shutil.copy2(ROOT / 'cad' / name, root / 'cad' / name)
            path = root / 'cad/selected-mechanism.json'
            cfg = json.loads(path.read_text())
            with patch.object(mechanism_study, 'ROOT', root):
                for depth, roof_hit in [(45, True), (10, False)]:
                    cfg['underbody_depth_assumption'] = depth
                    path.write_text(json.dumps(cfg))
                    doc, _, report = mechanism_study.build_study()
                    try:
                        with self.subTest(depth=depth):
                            self.assertTrue(all(report['geometry_checks'].values()))
                            self.assertFalse(report['fit']['installation_released'])
                            self.assertFalse(report['fit']['dimensions_confirmed'])
                            self.assertIn(str(depth), doc.getObject('UnderbodyReservation').Label)
                            self.assertIsNotNone(doc.getObject('KitCurvedArm'))
                            self.assertIsNone(doc.getObject('Mechanism'))
                            overlaps = {x['part'] for x in report['fit']['underbody_overlaps']}
                            self.assertEqual('AcousticRoof' in overlaps, roof_hit)
                            self.assertEqual(report['fit']['additional_roof_clearance_needed_mm'], max(0, depth - 14))
                    finally:
                        App.closeDocument(doc.Name)


if __name__ == '__main__':
    unittest.main()
