"""Physical rear-panel opening and conservative mains-entry fit checks."""
import json
import math
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


class ACInletTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / 'cad').mkdir()
        self.p = json.loads((ROOT / 'cad/parameters.json').read_text())
        (root / 'cad/parameters.json').write_text(json.dumps(self.p))
        with patch.object(build_model, 'ROOT', root):
            self.doc, _, _ = build_model.build()
        self.addCleanup(App.closeDocument, self.doc.Name)

    def test_rear_has_rounded_slot_and_two_through_bolt_holes(self):
        back = self.doc.Back.Shape
        # Horizontal mounting: slot x=46..94, z=94..122; screw centres z=88/128.
        for x, z in [(70, 108), (47, 108), (93, 108), (70, 95),
                     (70, 121), (70, 88), (70, 128)]:
            with self.subTest(x=x, z=z):
                probe = Part.makeCylinder(0.1, 12, App.Vector(x, 338, z), App.Vector(0, 1, 0))
                self.assertLess(back.common(probe).Volume, 1e-6)
        # R3 must retain wood in the corner, and material between slot and bolts.
        for x, z in [(46.1, 94.1), (70, 91), (70, 125)]:
            self.assertTrue(back.isInside(App.Vector(x, 344, z), 1e-6, False))
        blank_volume = 426 * 12 * 112
        port_volume = math.pi * 18**2 * 9 + math.pi * 24**2 * 3
        slot_area = 48 * 28 - (4 - math.pi) * 3**2
        removed = 12 * (slot_area + 2 * math.pi * 2.25**2)
        self.assertAlmostEqual(back.Volume, blank_volume - port_volume - removed, places=5)

    def test_fit_checks_reject_blocked_wiring_space_and_filled_slot(self):
        self.assertIsNotNone(self.doc.getObject('ACInlet'))
        checks, metrics = validate_model.check_ac_inlet(self.doc, self.p)
        self.assertTrue(all(checks.values()), (checks, metrics))
        obstacle = self.doc.addObject('Part::Feature', 'TestObstruction')
        obstacle.Shape = Part.makeBox(10, 5, 10, App.Vector(65, 305, 102))
        checks, _ = validate_model.check_ac_inlet(self.doc, self.p)
        self.assertFalse(checks['ac_inlet_wiring_space_clear'])
        self.doc.Back.Shape = self.doc.Back.Shape.fuse(
            Part.makeBox(10, 12, 10, App.Vector(65, 338, 103)))
        checks, _ = validate_model.check_ac_inlet(self.doc, self.p)
        self.assertFalse(checks['ac_inlet_panel_cutouts_match'])
