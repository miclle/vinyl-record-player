"""Read back the finished cover and its real landing/cavity from saved CAD."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import FreeCAD as App
import Part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from assembly_pose import set_cover_angle
from dust_cover import dimensions


class DustCoverTests(unittest.TestCase):
    def test_saved_cover_size_thickness_landing_and_measured_arm_clearance(self):
        p = json.loads((ROOT/'cad/parameters.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'CoverReadback.FCStd'
            shutil.copy2(ROOT/'cad/record-player.FCStd', path)
            doc = App.openDocument(str(path))
            try:
                self.assertEqual(float(doc.AssemblyState.CoverAngle), 70)
                set_cover_angle(doc, p, 0)
                shape = doc.DustCover.Shape
                b = shape.optimalBoundingBox(False)
                self.assertTrue(shape.isValid())
                self.assertEqual(len(shape.Solids), 1)
                for actual, expected in zip(
                        [b.XMin,b.YMin,b.ZMin,b.XLength,b.YLength,b.ZLength],
                        [0,1,146.5,450,348,75]):
                    self.assertAlmostEqual(actual, expected)
                # Reconstruct a solid shell independently, including the actual drilled holes.
                expected = Part.makeBox(450,348,75,App.Vector(0,1,146.5)).cut(
                    Part.makeBox(444,342,75,App.Vector(3,4,143.5)))
                for x in (83,117,333,367):
                    expected = expected.cut(Part.makeCylinder(2.75,5,App.Vector(x,345,164),App.Vector(0,1,0)))
                self.assertLess(expected.cut(shape).Volume, 1e-6)
                self.assertLess(shape.cut(expected).Volume, 1e-6)
                for name in ('SideLeft','SideRight','Back','Fascia'):
                    other = doc.getObject(name).Shape
                    self.assertAlmostEqual(shape.distToShape(other)[0], 0)
                    self.assertLess(shape.common(other).Volume, 1e-6)
                self.assertAlmostEqual(doc.FloatingDeck.Shape.optimalBoundingBox(False).ZMax, b.ZMin)
                self.assertAlmostEqual(b.ZMax-3-b.ZMin-p['cover_measured_arm_height'], 12)
                self.assertEqual([dimensions(p)[k] for k in ('inner_width','inner_depth','inner_height')], [444,342,72])
                self.assertAlmostEqual(doc.HingeSpacer0.Shape.optimalBoundingBox(False).YLength,1)
            finally:
                App.closeDocument(doc.Name)

    def test_inconsistent_height_and_landing_are_rejected(self):
        p = json.loads((ROOT/'cad/parameters.json').read_text())
        for key, value in [('cover_bottom',147.5),('closed_height',210.7),('cover_wall',80),('cover_height',float('nan'))]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                dimensions(dict(p, **{key:value}))


if __name__ == '__main__':
    unittest.main()
