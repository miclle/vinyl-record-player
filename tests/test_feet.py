"""Bought-in feet must fit the saved bottom panel without masking collisions."""
import json
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
import validate_model


class FeetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / 'cad').mkdir()
        (root / 'cad/parameters.json').write_bytes((ROOT / 'cad/parameters.json').read_bytes())
        (root / 'cad/mechanism.json').write_bytes((ROOT / 'cad/mechanism.json').read_bytes())
        with patch.object(build_model, 'ROOT', root):
            doc, self.p, _ = build_model.deliver()
        App.closeDocument(doc.Name)
        self.doc = App.openDocument(str(root / 'cad/record-player.FCStd'))
        self.addCleanup(App.closeDocument, self.doc.Name)

    def test_saved_bought_parts_and_bottom_holes_fit(self):
        self.assertIsNotNone(self.doc.getObject('FootMount0'), 'purchased foot mount missing')
        for i, (x, y) in enumerate([(33, 40), (417, 40), (33, 320), (417, 320)]):
            foot = self.doc.getObject(f'Foot{i}').Shape
            mount = self.doc.getObject(f'FootMount{i}').Shape
            bb = foot.optimalBoundingBox(False)
            self.assertAlmostEqual(bb.ZMin, 0)
            self.assertAlmostEqual(bb.ZMax, 43)
            self.assertAlmostEqual(bb.XLength, 30)
            rubber = foot.common(Part.makeBox(50, 50, 20, App.Vector(x-25, y-25, 0)))
            self.assertAlmostEqual(rubber.Volume, 3.141592653589793 * 15**2 * 20, places=5)
            stem = foot.common(Part.makeBox(50, 50, 23, App.Vector(x-25, y-25, 20)))
            self.assertAlmostEqual(stem.Volume, 3.141592653589793 * 4**2 * 23, places=5)
            mb = mount.optimalBoundingBox(False)
            for actual, expected in zip([mb.XLength, mb.YLength, mb.ZMin, mb.ZMax], [37, 37, 20, 37]):
                self.assertAlmostEqual(actual, expected)
            self.assertLess(foot.common(mount).Volume, 1e-5)
            for part in (foot, mount):
                self.assertLess(part.common(self.doc.Bottom.Shape).Volume, 1e-5)
            # Through centre clearance; blind pilot holes must leave 4 mm of wood.
            self.assertFalse(self.doc.Bottom.Shape.isInside(App.Vector(x, y, 30), 1e-6, False))
            self.assertFalse(self.doc.Bottom.Shape.isInside(App.Vector(x+14, y, 27), 1e-6, False))
            self.assertTrue(self.doc.Bottom.Shape.isInside(App.Vector(x+14, y, 33), 1e-6, False))
        self.assertAlmostEqual(self.doc.Bottom.Shape.optimalBoundingBox(False).ZMin, 22.5)
        self.assertAlmostEqual(self.doc.SideLeft.Shape.optimalBoundingBox(False).ZLength, 124)
        self.assertAlmostEqual(self.doc.Woofer.Shape.optimalBoundingBox(False).ZMin, 19.5)

    def test_validator_rejects_filled_center_hole_and_mount_collision(self):
        self.assertTrue(hasattr(validate_model, 'check_feet'), 'foot installation checks missing')
        checks, metrics = validate_model.check_feet(self.doc, self.p)
        self.assertTrue(all(checks.values()), (checks, metrics))
        original = self.doc.Bottom.Shape.copy()
        self.doc.Bottom.Shape = original.fuse(Part.makeCylinder(6.2, 12, App.Vector(33, 40, 22.5)))
        checks, _ = validate_model.check_feet(self.doc, self.p)
        self.assertFalse(checks['feet_bottom_cutouts_match'])
        self.assertFalse(checks['feet_installation_clear'])
        self.doc.Bottom.Shape = original
        self.doc.FootMount0.Placement.Base = App.Vector(0, -10, 0)
        checks, metrics = validate_model.check_feet(self.doc, self.p)
        self.assertFalse(checks['feet_parts_match'])
        self.assertFalse(checks['feet_installation_clear'])
        self.assertTrue(any(hit['other'] == 'Baffle' for hit in metrics['collisions']))

    def test_missing_mount_leaks_satellite_chamber(self):
        checks, _ = validate_model.check_acoustics(self.doc, self.p, [])
        self.assertTrue(checks['three_independent_enclosed_chambers'])
        self.doc.removeObject('FootMount0')
        self.doc.recompute()
        checks, _ = validate_model.check_acoustics(self.doc, self.p, [])
        self.assertFalse(checks['three_independent_enclosed_chambers'])
