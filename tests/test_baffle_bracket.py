"""Saved bracket size, mating faces, collision and print-export checks."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import FreeCAD as App
import Part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_baffle_bracket as bracket


class BaffleBracketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = json.loads((ROOT / 'cad/parameters.json').read_text())
        cls.shape, cls.data = bracket.build(cls.p)

    def test_requested_envelope_and_actual_joint_angle(self):
        bounds = self.shape.optimalBoundingBox(False)
        for actual, expected in zip((bounds.XLength, bounds.YLength, bounds.ZLength), (50, 50, 50)):
            self.assertAlmostEqual(actual, expected, places=6)
        self.assertAlmostEqual(bounds.ZMin, 0, places=6)
        self.assertEqual(self.data['wall_thickness_mm'], 6)
        self.assertFalse(self.shape.isInside(App.Vector(25, 25, 20), 1e-6, True))
        for point in ((25, 20, 3), (3, 25, 20), (47, 25, 20)):
            self.assertTrue(self.shape.isInside(App.Vector(*point), 1e-6, False))
        self.assertAlmostEqual(self.data['joint_angle_deg'], 72, places=6)
        self.assertAlmostEqual(self.data['top_setback_mm'], 16.245984811645318, places=6)
        changed = copy.deepcopy(self.p)
        changed['front_angle'] = 60
        shape, data = bracket.build(changed)
        self.assertTrue(shape.isValid())
        self.assertAlmostEqual(data['top_setback_mm'], 50 / (3 ** 0.5), places=6)
        changed['front_angle'] = 40
        with self.assertRaisesRegex(ValueError, 'no usable bracket'):
            bracket.build(changed)

    def test_saved_assembly_full_contacts_and_no_collisions(self):
        source = ROOT / 'cad/record-player.FCStd'
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        fit = bracket.check_fit(self.shape, self.data, self.p)
        self.assertEqual(fit['model_sha256'], before)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        self.assertEqual(len(fit['positions']), 2)
        for position in fit['positions']:
            self.assertEqual(position['overlap_mm3'], 0)
            self.assertGreater(position['checked_physical_objects'], 60)
            self.assertAlmostEqual(position['contact_area_mm2']['Bottom'], self.data['bottom_contact_area_mm2'], places=6)
            self.assertAlmostEqual(position['contact_area_mm2']['Baffle'], self.data['baffle_contact_area_mm2'], places=6)
        shifted = copy.deepcopy(self.data)
        shifted['installation_root_yz_mm'][0] += 0.5
        with self.assertRaisesRegex(ValueError, 'Incomplete Baffle contact'):
            bracket.check_fit(self.shape, shifted, self.p)

    def test_containment_in_compound_and_stale_parameters_are_rejected(self):
        stale = copy.deepcopy(self.p)
        stale['front_angle'] = 71
        with self.assertRaisesRegex(ValueError, 'Saved assembly parameters differ'):
            bracket.check_fit(self.shape, self.data, stale)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'ObstructedBracket.FCStd'
            source.write_bytes((ROOT / 'cad/record-player.FCStd').read_bytes())
            doc = App.openDocument(str(source))
            try:
                obj = doc.addObject('Part::Feature', 'ContainmentTest')
                obj.Shape = Part.makeCompound([
                    Part.makeBox(10, 60, 60, App.Vector(165, 25, 34)),
                    Part.makeBox(1, 1, 1, App.Vector(500, 500, 500))])
                doc.recompute()
                doc.save()
            finally:
                App.closeDocument(doc.Name)
            with self.assertRaisesRegex(ValueError, 'overlaps ContainmentTest'):
                bracket.check_fit(self.shape, self.data, self.p, source)

    def test_saved_cad_step_and_stl_match(self):
        result = bracket.verify_exports(bracket.OUTPUT, self.shape)
        self.assertEqual(result['solid_count'], 1)
        self.assertTrue(result['cad_step_readback_match'])
        self.assertTrue(result['closed_mesh'])
        self.assertEqual(result['mesh_components'], 1)
        report = json.loads((bracket.OUTPUT / 'Baffle-bracket.json').read_text())
        self.assertEqual(report['validation'], result)
        self.assertEqual(report['assembly_fit'], bracket.check_fit(self.shape, self.data, self.p))

    def test_four_normal_through_holes_and_small_chamfers(self):
        self.assertEqual(self.data['hole_count'], 4)
        cylinders = [face.Surface for face in self.shape.Faces
                     if isinstance(face.Surface, Part.Cylinder)]
        cones = [face.Surface for face in self.shape.Faces
                 if isinstance(face.Surface, Part.Cone)]
        self.assertEqual(len(cylinders), 4)
        self.assertEqual(len(cones), 8)
        for surface in cylinders:
            self.assertAlmostEqual(surface.Radius, 2, places=6)
        for hole in self.data['holes']:
            center = App.Vector(*hole['center_mm'])
            axis = App.Vector(*hole['inward_axis'])
            tangent = App.Vector(1, 0, 0)
            # Bore is clear through 6 mm; radius 2.1 is material in its middle.
            probe = Part.makeCylinder(1.99, 6, center, axis)
            self.assertLess(probe.common(self.shape).Volume, 1e-6)
            self.assertTrue(self.shape.isInside(center + axis * 3 + tangent * 2.1, 1e-6, False))
            self.assertFalse(self.shape.isInside(center + axis * 0.1 + tangent * 2.15, 1e-6, True))
            self.assertTrue(self.shape.isInside(center + axis * 0.1 + tangent * 2.25, 1e-6, False))
            self.assertFalse(self.shape.isInside(center + axis * 5.9 + tangent * 2.15, 1e-6, True))
            # Nominal Ø8 x 30 mm straight tool envelope from the inner mouth.
            access = Part.makeCylinder(4, 30, center + axis * 6.01, axis)
            self.assertLess(access.common(self.shape).Volume, 1e-6)

    def test_saved_gui_visibility_and_camera(self):
        with ZipFile(bracket.OUTPUT / 'Baffle-bracket.FCStd') as archive:
            gui = ET.fromstring(archive.read('GuiDocument.xml'))
        provider = gui.find('.//ViewProvider[@name="BaffleBracket"]')
        self.assertIsNotNone(provider)
        self.assertEqual(provider.find('Properties/Property[@name="Visibility"]/Bool').get('value'), 'true')
        self.assertTrue(gui.find('Camera').get('settings'))

    @unittest.skipIf(App.GuiUp, 'Headless export boundary only')
    def test_headless_export_cannot_replace_gui_document(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'export'
            with self.assertRaisesRegex(RuntimeError, 'FreeCAD GUI'):
                bracket.export(output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
