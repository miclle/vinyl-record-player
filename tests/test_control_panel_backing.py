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
        return self.shape.isInside(App.Vector(x, 170-y, 1), 1e-6, False)

    def test_stepped_outline_and_thickness(self):
        box = self.shape.optimalBoundingBox(False)
        for actual, target in zip((box.XMin, box.XMax, box.YMin, box.YMax, box.ZMin, box.ZMax),
                                  (-65, 70, 0, 170, 0, 12)):
            self.assertAlmostEqual(actual, target, places=6)
        self.assertFalse(self.contains(-4, 29.9))
        self.assertTrue(self.contains(-4, 30.1))
        self.assertTrue(self.contains(1, 15))
        self.assertTrue(self.contains(-7.9, 159.9))
        self.assertFalse(self.contains(-8.1, 90))
        self.assertTrue(self.contains(-64.9, 31))
        self.assertTrue(self.contains(-64.9, 160))
        self.assertFalse(self.contains(-30, 165.01))
        self.assertFalse(self.contains(-7.9, 169.9))
        self.assertTrue(self.contains(69.99, 90))
        for y in (0.1,5,165.01,169.9):
            self.assertFalse(self.contains(-0.01,y))
            self.assertTrue(self.contains(0.01,y))
            self.assertTrue(self.contains(69.99,y))
            self.assertFalse(self.contains(70.01,y))

    def test_three_ribs_flush_joints_and_model_clearance(self):
        # Vertical rib Y=33..162 and horizontal ribs X=-65..-5 stop flush at both joints.
        probe = Part.makeBox(3,125,10,App.Vector(-8,9,2))
        self.assertLess(probe.cut(self.shape).Volume,1e-6)
        # Read the saved top faces directly, avoiding a near-tangent OCCT boolean.
        high = Part.makeCompound([f for f in self.shape.Faces
                                  if abs(f.CenterOfMass.z-12)<1e-6
                                  and abs(f.normalAt(0,0).z-1)<1e-6])
        b = high.optimalBoundingBox(False)
        for actual,target in zip((b.XMin,b.XMax,b.YMin,b.YMax),(-65,-5,8,137)):
            self.assertAlmostEqual(actual,target,places=6)
        # Equal inner additions and outer removals preserve the total top area.
        self.assertAlmostEqual(high.Area,3*129+2*60*3-2*3*3,places=5)
        self.assertFalse(self.shape.isInside(App.Vector(-6.5,137.01,3),1e-6,False))
        self.assertFalse(self.shape.isInside(App.Vector(-4.99,50,3),1e-6,False))
        original_plate_envelope = Part.makeBox(70,170,3.5,App.Vector(0,0,2))
        self.assertLess(self.shape.common(original_plate_envelope).Volume,1e-6)
        mesh = backing.Mesh.Mesh(str(backing.OUTPUT / f"{backing.STEM}.stl"))
        self.assertAlmostEqual(mesh.BoundBox.ZMin,0,places=6)
        self.assertAlmostEqual(mesh.BoundBox.ZMax,12,places=6)
        self.assertAlmostEqual(mesh.BoundBox.XLength,135,places=6)
        for y in (134,5):
            arm=Part.makeBox(65,6,2,App.Vector(-65,y,0))
            self.assertLess(arm.cut(self.shape).Volume,1e-6)
        for y in (134,8):
            lip=Part.makeBox(57,3,10,App.Vector(-65,y,2))
            self.assertLess(lip.cut(self.shape).Volume,1e-6)
        self.assertFalse(self.shape.isInside(App.Vector(-30,133.99,3),1e-6,False))
        self.assertFalse(self.shape.isInside(App.Vector(-30,11.01,3),1e-6,False))
        # Probe all four trimmed ends, plus the retired upper strip location.
        self.assertFalse(self.shape.isInside(App.Vector(-6.5,7.99,3),1e-6,False))
        for y in (135.5,9.5):
            self.assertFalse(self.shape.isInside(App.Vector(-4.99,y,3),1e-6,False))
        self.assertFalse(self.contains(-30,2))
        self.assertTrue(self.contains(-30,31))
        self.assertTrue(self.contains(-30,35))
        self.assertFalse(self.contains(-30,311.01))

    def test_clear_window_lower_pcb_relief_and_screw_support(self):
        self.assertFalse(self.contains(2.81, 12.01))
        self.assertFalse(self.contains(62.19, 147.99))
        self.assertTrue(self.contains(2.79, 90))
        self.assertTrue(self.contains(62.21, 90))
        self.assertFalse(self.contains(45, 157))
        self.assertTrue(self.contains(45, 158.01))
        self.assertFalse(self.contains(45, 157.99))
        self.assertFalse(self.contains(14.49, 157.5))
        self.assertFalse(self.contains(14.51, 157.5))
        self.assertFalse(self.contains(50.49, 157.5))
        self.assertFalse(self.contains(50.51, 157.5))
        for x in (3,9.5,32.5,60.5,62):
            self.assertFalse(self.contains(x,157.99))
            self.assertTrue(self.contains(x,158.01))
        cylinders = [f.Surface for f in self.shape.Faces if isinstance(f.Surface, Part.Cylinder)
                     and abs(f.Surface.Radius-1.75)<1e-6]
        self.assertEqual(len(cylinders), 4)
        for x,y in ((9.5,6),(60.5,6),(9.5,164),(60.5,164)):
            self.assertFalse(self.contains(x,y))
            self.assertTrue(self.contains(x+1.76,y))
            self.assertEqual(sum(abs(s.Center.x-x)<1e-6 and abs(s.Center.y-(170-y))<1e-6
                                 and abs(s.Radius-1.75)<1e-6 for s in cylinders), 1)
            head = Part.makeCylinder(3.5,2,App.Vector(x,170-y,0))
            bore = Part.makeCylinder(1.75,2,App.Vector(x,170-y,0))
            self.assertLess(head.cut(bore).cut(self.shape).Volume,1e-6)

    def test_inner_junction_rounds_have_requested_radii_and_bed_support(self):
        for radius,x,y in ((3,-11,39),(1,-9,158)):
            faces = [f for f in self.shape.Faces if isinstance(f.Surface,Part.Cylinder)
                     and abs(f.Surface.Radius-radius)<1e-6
                     and abs(f.Surface.Center.x-x)<1e-6
                     and abs(f.Surface.Center.y-(170-y))<1e-6]
            self.assertEqual(len(faces),1)
            b=faces[0].optimalBoundingBox(False)
            self.assertAlmostEqual(b.ZMin,0,places=6)
            self.assertAlmostEqual(b.ZMax,12,places=6)
        for z in (0.1,1,2.1,11.9):
            for x,y in ((-8.1,36.1),(-8.1,158.9)):
                self.assertTrue(self.shape.isInside(App.Vector(x,170-y,z),1e-6,False))
            for x,y in ((-10.9,38.9),(-8.9,158.1)):
                self.assertFalse(self.shape.isInside(App.Vector(x,170-y,z),1e-6,False))

    def test_outer_junction_rounds_preserve_plate_and_rib_connection(self):
        for radius,x,y in ((3,-8,36),(1,-6,161)):
            faces = [f for f in self.shape.Faces if isinstance(f.Surface,Part.Cylinder)
                     and abs(f.Surface.Radius-radius)<1e-6
                     and abs(f.Surface.Center.x-x)<1e-6
                     and abs(f.Surface.Center.y-(170-y))<1e-6]
            self.assertEqual(len(faces),1)
            b=faces[0].optimalBoundingBox(False)
            self.assertAlmostEqual(b.ZMin,2,places=6)
            self.assertAlmostEqual(b.ZMax,12,places=6)
        for x,y in ((-5.1,33.1),(-5.1,161.9)):
            self.assertTrue(self.contains(x,y))
            self.assertFalse(self.shape.isInside(App.Vector(x,170-y,3),1e-6,False))
        for x,y in ((-7,35),(-6,160)):
            self.assertTrue(self.shape.isInside(App.Vector(x,170-y,11.9),1e-6,False))

    def test_symmetric_twelve_mm_bottom_band_with_stationary_left_arms(self):
        # Hole center Y=164 lies 6 mm from both Y=158 and Y=170 edges.
        band=Part.makeBox(70,12,2,App.Vector(0,0,0))
        for x in (9.5,60.5):
            band=band.cut(Part.makeCylinder(1.75,2,App.Vector(x,6,0)))
        self.assertLess(band.cut(self.shape).Volume,1e-6)
        for y in (158.01,162.5,169.99):
            self.assertTrue(self.contains(32.5,y))
        opening=backing.layout(backing.load_parameters(),backing.panel.load_parameters())[1]
        inner_edge=max(y for x,y in opening)
        for x in (9.5,60.5):
            self.assertAlmostEqual(164-inner_edge,170-164,places=6)
            for offset in (-4,-2,2,4):
                self.assertEqual(self.contains(x,164+offset),self.contains(x,164-offset))
        self.assertFalse(self.contains(9.5,165.5))
        self.assertFalse(self.contains(60.5,165.5))

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
        plate = Part.makeBox(70,170,3.5)
        self.assertLess(installed.common(plate).Volume,1e-6)


if __name__ == '__main__':
    unittest.main()
