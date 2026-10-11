"""Saved print tools, clearance and unobstructed removal; no main CAD mutation."""
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import FreeCAD as App
import Part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_grille_jigs as jigs


class GrilleJigsTests(unittest.TestCase):
    def test_requested_slots_print_envelope_and_glue_clearance(self):
        shape = jigs.build_single()
        bounds = shape.optimalBoundingBox(False)
        self.assertEqual(len(shape.Solids), 1)
        for actual, expected in zip((bounds.XLength, bounds.YLength, bounds.ZLength),
                                    (32, 90 - jigs.floor_line_y(0), 10)):
            self.assertAlmostEqual(actual, expected, places=6)
        self.assertAlmostEqual(bounds.ZMin, 0, places=6)
        for i in range(7):
            low, high = jigs.slot_bounds(i)
            self.assertAlmostEqual(high - low, 6.3, places=6)
            probe = Part.makeBox(22, 6.299, 6, App.Vector(0, low + 0.0005, 3.5))
            self.assertLess(probe.common(shape).Volume, 1e-7)
            for y in (low - 0.05, high + 0.05):
                self.assertTrue(shape.isInside(App.Vector(11, y, 5), 1e-7, False))
            self.assertTrue(shape.isInside(App.Vector(11, (low + high) / 2, 1.5), 1e-7, False))
        board = Part.makeBox(100, 100, 2, App.Vector(-10, -5, 13))
        self.assertAlmostEqual(shape.distToShape(board)[0], 3, places=6)

    def test_nominal_and_oversize_wood_do_not_bind_during_removal(self):
        original = jigs.build_single()
        for width in (6.0, 6.2):
            wood = jigs.wood_fixture(width)
            for distance in (0, 0.1, 1, 3, 6.6, 7, 10):
                moving = original.copy()
                moving.translate(App.Vector(0, 0, -distance))
                self.assertLess(sum(moving.common(solid).Volume for solid in wood.Solids), 1e-7)
        # An oversized strip must be caught by the slot-fit check.
        self.assertGreater(sum(original.common(s).Volume for s in jigs.wood_fixture(6.5).Solids), 1)

    def test_horizontal_stop_six_mm_datum_and_outward_removal(self):
        for angle in (60, 72, 80):
            shape = jigs.build_single(angle)
            result = jigs.verify_installation(shape, angle)
            self.assertAlmostEqual(result['bottom_gap_vertical_mm'], 6, places=6)
            self.assertTrue(result['normal_removal_clear'])
            installed = shape.copy()
            installed.Placement = jigs.installation_placement(angle_deg=angle)
            self.assertAlmostEqual(installed.optimalBoundingBox(False).ZMin, 0, places=6)
        for angle in (0, 90):
            with self.assertRaises(ValueError):
                jigs.build_single(angle)

    def test_single_saved_exports(self):
        result = jigs.verify_exports()
        self.assertEqual(result['solid_count'], 1)
        self.assertEqual(result['mesh_components'], 1)
        self.assertAlmostEqual(result['installation']['bottom_gap_vertical_mm'], 6, places=6)
        with ZipFile(jigs.OUTPUT / (jigs.STEM + '.FCStd')) as archive:
            gui = ET.fromstring(archive.read('GuiDocument.xml'))
            visibility = gui.findall('.//Property[@name="Visibility"]/Bool')
            self.assertEqual(len(visibility), 1)
            self.assertTrue(all(value.get('value') == 'true' for value in visibility))


if __name__ == '__main__':
    unittest.main()
