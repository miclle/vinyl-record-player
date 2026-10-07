"""Acceptance of saved backing, alignment, rib clearance and printable exports."""
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import FreeCAD as App
import Part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_control_panel_backing as backing


class BackingTests(unittest.TestCase):
    def setUp(self):
        self.doc = App.openDocument(str(backing.OUTPUT / f'{backing.STEM}.FCStd'))
        self.doc_name = self.doc.Name
        self.shape = self.doc.Backing.Shape

    def tearDown(self):
        if self.doc_name in App.listDocuments():
            App.closeDocument(self.doc_name)

    def contains(self, x, y):
        return self.shape.isInside(App.Vector(x, 160-y, 1), 1e-6, False)

    def test_stepped_outline_and_thickness(self):
        box = self.shape.optimalBoundingBox(False)
        for actual, target in zip((box.XMin, box.XMax, box.YMin, box.YMax, box.ZMin, box.ZMax),
                                  (-8, 65, 0, 160, 0, 8)):
            self.assertAlmostEqual(actual, target, places=6)
        self.assertFalse(self.contains(-4, 29.9))
        self.assertTrue(self.contains(-4, 30.1))
        self.assertTrue(self.contains(1, 15))
        self.assertTrue(self.contains(-7.9, 159.9))
        self.assertFalse(self.contains(-8.1, 90))

    def test_front_left_rib_height_width_length_and_clearance(self):
        # Full 130 mm strip, 3 mm wide and 6 mm above the 2 mm plate; total height 8 mm.
        probe = Part.makeBox(3,130,6,App.Vector(-8,0,2))
        self.assertLess(probe.cut(self.shape).Volume,1e-6)
        high = self.shape.common(Part.makeBox(80,160,5.8,App.Vector(-10,0,2.1)))
        b = high.optimalBoundingBox(False)
        for actual,target in zip((b.XMin,b.XMax,b.YMin,b.YMax),(-8,-5,0,130)):
            self.assertAlmostEqual(actual,target,places=6)
        self.assertAlmostEqual(high.Volume,3*130*5.8,places=5)
        self.assertFalse(self.shape.isInside(App.Vector(-6.5,130.1,3),1e-6,False))
        self.assertFalse(self.shape.isInside(App.Vector(-4.99,50,3),1e-6,False))
        original_plate_envelope = Part.makeBox(65,160,3.5,App.Vector(0,0,2))
        self.assertLess(self.shape.common(original_plate_envelope).Volume,1e-6)
        mesh = backing.Mesh.Mesh(str(backing.OUTPUT / f"{backing.STEM}.stl"))
        self.assertAlmostEqual(mesh.BoundBox.ZMin,0,places=6)
        self.assertAlmostEqual(mesh.BoundBox.ZMax,8,places=6)
        self.assertAlmostEqual(mesh.BoundBox.XLength,73,places=6)

    def test_clear_window_lower_pcb_relief_and_screw_support(self):
        self.assertFalse(self.contains(2.81, 12.01))
        self.assertFalse(self.contains(62.19, 147.99))
        self.assertTrue(self.contains(2.79, 90))
        self.assertTrue(self.contains(62.21, 90))
        self.assertFalse(self.contains(45, 157))
        self.assertTrue(self.contains(45, 158.01))
        self.assertTrue(self.contains(14.49, 154))
        self.assertFalse(self.contains(14.51, 154))
        self.assertFalse(self.contains(50.49, 154))
        self.assertTrue(self.contains(50.51, 154))
        cylinders = [f.Surface for f in self.shape.Faces if isinstance(f.Surface, Part.Cylinder)]
        self.assertEqual(len(cylinders), 4)
        for x,y in ((9.5,6),(55.5,6),(9.5,154),(55.5,154)):
            self.assertFalse(self.contains(x,y))
            self.assertTrue(self.contains(x+1.76,y))
            self.assertEqual(sum(abs(s.Center.x-x)<1e-6 and abs(s.Center.y-(160-y))<1e-6
                                 and abs(s.Radius-1.75)<1e-6 for s in cylinders), 1)
            head = Part.makeCylinder(3.5,2,App.Vector(x,160-y,0))
            bore = Part.makeCylinder(1.75,2,App.Vector(x,160-y,0))
            self.assertLess(head.cut(bore).cut(self.shape).Volume,1e-6)

    def test_saved_export_topology_and_rib_alignment(self):
        p, front = backing.load_parameters(), backing.panel.load_parameters()
        result = backing.verify_exports(backing.OUTPUT, backing.build(p,front), p, front)
        self.assertTrue(result['passed'])
        with ZipFile(backing.OUTPUT / f'{backing.STEM}.FCStd') as archive:
            xml = ET.fromstring(archive.read('GuiDocument.xml'))
            provider = xml.find('.//ViewProvider[@name="Backing"]')
            self.assertEqual(provider.find('.//Property[@name="Visibility"]/Bool').get('value'), 'true')
        installed = self.shape.copy()
        installed.translate(App.Vector(0,0,-2))
        for x in (3.1,60.4):
            rib = Part.makeBox(1.5,135.4,10,App.Vector(x,12.3,-10))
            self.assertLess(installed.common(rib).Volume,1e-6)


if __name__ == '__main__':
    unittest.main()
