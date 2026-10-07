"""Independent print geometry and fastening paths; no main-assembly modification."""
import copy
import hashlib
import json
import math
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
import build_chamber_roofs as roofs


class ChamberRoofsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = roofs.load_config()
        cls.parts = roofs.build(cls.config)

    def test_measured_dimensions_and_post_counts(self):
        expected = {'FullrangeLeft': [117, 108, 22], 'FullrangeRight': [119, 110, 22],
                    'WooferFront': [167, 148, 22], 'WooferRear': [167, 147.8, 22]}
        for name, part in self.parts.items():
            shape = part['installed']
            self.assertTrue(shape.isValid())
            self.assertEqual(len(shape.Solids), 1)
            self.assertEqual(len(part['holes']), 4)
            for actual, wanted in zip(roofs.bounds(shape), expected[name]):
                self.assertAlmostEqual(actual, wanted, places=6)
            thickness = 5 if name.startswith('Fullrange') else 8
            self.assertAlmostEqual(shape.optimalBoundingBox(False).ZMax, thickness)
            sample_y = 220 if name == 'WooferRear' else 50
            center_strip = shape.common(Part.makeBox(10, 10, 40, App.Vector(50, sample_y, -20)))
            self.assertAlmostEqual(center_strip.optimalBoundingBox(False).ZLength, thickness)
            for hole in part['holes']:
                x, y, z = hole['wall_entry_mm']
                # Material beside each bore proves a complete post at that side wall.
                self.assertTrue(shape.isInside(App.Vector(x + (0.1 if hole['side'] == 'Left' else -0.1), y + 4, z), 1e-6, True))
        full_woofer = self.parts['WooferFront']['installed'].fuse(self.parts['WooferRear']['installed'])
        self.assertAlmostEqual(full_woofer.optimalBoundingBox(False).YLength, 284)

    def test_45_degree_free_bores_heads_and_driver_access(self):
        for part in self.parts.values():
            shape = part['installed']
            for hole in part['holes']:
                center = App.Vector(*hole['head_seat_center_mm'])
                axis = App.Vector(*hole['outward_down_axis'])
                self.assertAlmostEqual(axis.Length, 1)
                self.assertAlmostEqual(abs(axis.x), abs(axis.z))
                self.assertAlmostEqual(axis.y, 0)
                self.assertLess(axis.z, 0)
                bore = Part.makeCylinder(1.99, 19.2, center, axis)
                self.assertLess(shape.common(bore).Volume, 1e-6)
                screw = Part.makeCylinder(1.75, 18.2, center, axis)
                self.assertLess(shape.common(screw).Volume, 1e-6)
                # Measured diameter, trial head height 3 mm; head is not exported.
                head = Part.makeCylinder(3.8, 3, center, -axis)
                self.assertLess(shape.common(head).Volume, 1e-6)
                self.assertLess(head.optimalBoundingBox(False).ZMax, part['nominal_size_mm'][2])
                tool = Part.makeCylinder(4.09, 40, center, -axis)
                self.assertLess(shape.common(tool).Volume, 1e-6)
                # The pocket has a full flat annular seat beneath a pan-head proxy.
                self.assertTrue(shape.isInside(center + axis * 0.5 + App.Vector(0, 3, 0), 1e-6, False))

    def test_thin_plates_keep_full_annular_head_seat_backed_by_posts(self):
        for part in self.parts.values():
            for hole in part['holes']:
                center = App.Vector(*hole['head_seat_center_mm'])
                axis = App.Vector(*hole['outward_down_axis'])
                tangent = App.Vector(-axis.z, 0, axis.x)
                for radius in (2.6, 3.8):
                    for angle in range(0, 360, 15):
                        radians = math.radians(angle)
                        point = center + axis * 0.4 + tangent * (radius * math.cos(radians)) + App.Vector(0, radius * math.sin(radians), 0)
                        self.assertTrue(part['installed'].isInside(point, 1e-6, False),
                                        f'Missing head support at radius={radius}, angle={angle}')
        self.assertAlmostEqual(self.parts['FullrangeLeft']['holes'][0]['head_seat_center_mm'][2], -0.5)
        self.assertAlmostEqual(self.parts['WooferFront']['holes'][0]['head_seat_center_mm'][2], 2.5)

    def test_posts_touch_vertical_wood_without_overlap(self):
        for name in ('FullrangeLeft', 'FullrangeRight'):
            part = self.parts[name]
            width, length, thickness = part['nominal_size_mm']
            depth = part['mounting_datums']['post_depth_mm']
            shape = part['installed']
            for wall_x in (-10, width):
                wall = Part.makeBox(10, length + 20, 40, App.Vector(wall_x, -10, -20))
                self.assertLess(shape.common(wall).Volume, 1e-6)
                contact = sum(face.common(wall).Area for face in shape.Faces)
                expected = thickness * length + 2 * (depth * 12 - math.pi * 2**2 * math.sqrt(2))
                self.assertAlmostEqual(contact, expected, places=5)
            for hole in part['holes']:
                seat = App.Vector(*hole['head_seat_center_mm'])
                wall_entry = App.Vector(*hole['wall_entry_mm'])
                wood_length = 18.2 - (seat - wall_entry).Length
                self.assertAlmostEqual(wood_length, 6.1791847198, places=6)
                tip = seat + App.Vector(*hole['outward_down_axis']) * 18.2
                self.assertLess(tip.z, wall_entry.z)
                self.assertTrue(-10 < tip.x < 0 if hole['side'] == 'Left' else width < tip.x < width + 10)

    def test_lap_clearance_and_rear_first_installation(self):
        front = self.parts['WooferFront']['installed']
        rear = self.parts['WooferRear']['installed']
        self.assertLess(front.common(rear).Volume, 1e-6)
        p = App.Vector(80, 142, 4)
        self.assertFalse(front.isInside(p, 1e-6, True))
        self.assertFalse(rear.isInside(p, 1e-6, True))
        self.assertTrue(front.isInside(App.Vector(80, 142, 4.51), 1e-6, True))
        self.assertTrue(rear.isInside(App.Vector(80, 142, 3.49), 1e-6, True))
        crop = Part.makeBox(20, 4, 8, App.Vector(70, 140, 0))
        upper_box = front.common(crop).optimalBoundingBox(False)
        lower_box = rear.common(crop).optimalBoundingBox(False)
        self.assertAlmostEqual(upper_box.ZLength, 3.5)
        self.assertAlmostEqual(lower_box.ZLength, 3.5)
        self.assertAlmostEqual(upper_box.ZMin - lower_box.ZMax, 1)
        self.assertFalse(front.isInside(App.Vector(80, 148.1, 7), 1e-6, True))
        self.assertFalse(rear.isInside(App.Vector(80, 148.1, 7), 1e-6, True))
        for offset in range(0, 23):
            lowered = front.copy()
            lowered.translate(App.Vector(0, 0, offset))
            self.assertLess(lowered.common(rear).Volume, 1e-6)

    def test_print_orientation_and_machine_bounds(self):
        for part in self.parts.values():
            printed = part['printable']
            box = printed.optimalBoundingBox(False)
            self.assertAlmostEqual(box.ZMin, 0)
            self.assertLessEqual(max(part['print_size_mm']), 256)
            back = roofs.print_shape(printed)
            # Two rigid flips recover the same geometry translated to positive Z.
            expected = part['installed'].copy()
            original = expected.optimalBoundingBox(False)
            expected.translate(App.Vector(-original.XMin, -original.YMin, -original.ZMin))
            self.assertLess(expected.cut(back).Volume, 1e-6)
            self.assertLess(back.cut(expected).Volume, 1e-6)

    def test_invalid_fit_parameters_fail_before_export(self):
        changes = [('measured', 'satellite_plate_thickness', 20), ('measured', 'screw_length', 10),
                   ('trial', 'head_pocket_diameter', 7), ('trial', 'head_seat_below_top', 2),
                   ('trial', 'mount_total_height', 18), ('measured', 'lap_glue_gap', 8),
                   ('measured', 'screw_angle_from_vertical_deg', 30),
                   ('trial', 'woofer_hole_y', [22, 104, 145, 262]),
                   ('measured', 'printer_volume', [100, 256, 256])]
        for section, key, value in changes:
            config = copy.deepcopy(self.config)
            config[section][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                roofs.build(config)

    def test_saved_files_and_report_match_generated_parts(self):
        report = json.loads((roofs.OUTPUT / 'chamber-roofs.json').read_text())
        self.assertEqual(report['parameters'], self.config)
        self.assertEqual(roofs.verify_exports(roofs.OUTPUT, self.parts), report['validation'])
        for line in (roofs.OUTPUT / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            self.assertEqual(hashlib.sha256((roofs.OUTPUT / name).read_bytes()).hexdigest(), digest)

    def test_gui_visibility_camera_and_individual_geometry_only(self):
        for name in self.parts:
            with ZipFile(roofs.OUTPUT / (name + '.FCStd')) as archive:
                gui = ET.fromstring(archive.read('GuiDocument.xml'))
            provider = gui.find(f'.//ViewProvider[@name="{name}"]')
            self.assertEqual(provider.find('Properties/Property[@name="Visibility"]/Bool').get('value'), 'true')
            self.assertTrue(gui.find('Camera').get('settings'))
        doc = App.openDocument(str(roofs.OUTPUT / 'Chamber-roofs.FCStd'))
        try:
            self.assertEqual({o.Name for o in doc.Objects}, set(self.parts))
            for index, (name, part) in enumerate(self.parts.items()):
                expected = part['installed'].copy()
                expected.translate(App.Vector([0, 150, 310, 310][index], 0, 0))
                self.assertLess(doc.getObject(name).Shape.cut(expected).Volume, 1e-6)
                self.assertLess(expected.cut(doc.getObject(name).Shape).Volume, 1e-6)
                self.assertEqual(json.loads(doc.getObject(name).ParametersJSON), self.config)
        finally:
            App.closeDocument(doc.Name)

    @unittest.skipIf(App.GuiUp, 'Headless export boundary only')
    def test_headless_export_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'roofs'
            with self.assertRaisesRegex(RuntimeError, 'FreeCAD GUI'):
                roofs.export(output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
