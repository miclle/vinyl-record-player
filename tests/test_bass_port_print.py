"""D-port dimensions, sealed base, axial installation and saved printable geometry."""
import copy
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import FreeCAD as App
import Part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_bass_port_print as port


class BassPortPrintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = port.load_config()
        cls.parts, cls.metrics = port.build(cls.config)

    def test_measured_height_bore_and_normal_wall_thickness(self):
        c, d = self.config, port.datums(self.config)
        outer = port.profile_prism(c, 1)
        inner = port.profile_prism(c, 1, inside=True)
        self.assertAlmostEqual(outer.optimalBoundingBox(False).ZLength, 25)
        self.assertAlmostEqual(inner.optimalBoundingBox(False).ZLength, 19)
        # One mm long hollow section: the minimum surface separation is 3 mm.
        outer_face = min(outer.Faces, key=lambda f: abs(f.CenterOfMass.y))
        inner_face = min(inner.Faces, key=lambda f: abs(f.CenterOfMass.y))
        self.assertAlmostEqual(outer_face.OuterWire.distToShape(inner_face.OuterWire)[0], 3, places=6)
        self.assertAlmostEqual(d['radius'] * 2, 38)
        self.assertAlmostEqual(self.metrics['equivalent_round_bore_diameter_mm'], 23.05027674, places=6)
        self.assertLess(self.metrics['area_ratio_to_original_32mm_bore'], 0.6)

    def test_clock10_relief_and_constant_D_section_behind_panel(self):
        d = port.datums(self.config)
        self.assertEqual(self.config['trial']['clock10_radial_relief'], 10)
        self.assertAlmostEqual(d['radius'] - d['bevel'], 10)
        n = port.RELIEF_NORMAL
        self.assertLess(n.x, 0)
        self.assertGreater(n.z, 0)
        self.assertAlmostEqual(n.Length, 1)
        section = port.profile_prism(self.config, 1)
        # A point just inside the old circle at 10 o'clock must now be absent.
        self.assertFalse(section.isInside(n * (d['radius'] - 0.1) + App.Vector(0, 0.5, 0), 1e-6, False))
        self.assertFalse(section.isInside(n * 9.01 + App.Vector(0, .5, 0), 1e-6, False))
        self.assertTrue(section.isInside(n * 8.99 + App.Vector(0, .5, 0), 1e-6, False))
        tube = self.parts['BassPort']['installed']
        for y in (12.1, 20, 60, self.parts['BassPort']['insertion_length_mm'] - 2):
            strip = tube.common(Part.makeBox(100, 0.1, 100, App.Vector(-50, y, -50)))
            expected = (self.metrics['outer_section_area_mm2'] - self.metrics['bore_area_mm2']) * 0.1
            self.assertAlmostEqual(strip.Volume, expected, places=5)
            point = n * (d['bevel'] - 0.1) - App.Vector(n.z, 0, -n.x) * 4 + App.Vector(0, y, 0)
            self.assertTrue(tube.isInside(point, 1e-6, False))

    def test_round_hole_roof_post_and_axial_installation(self):
        for data in self.parts.values():
            result = port.verify_installation(self.config, data)
            self.assertTrue(result['outside_axial_path_clear'])
            self.assertTrue(result['unused_round_opening_covered'])
            self.assertFalse(result['actual_post_verified'])
        # Fixture checks must catch a body protruding outside the nominal round hole.
        data = dict(self.parts['BassPort'])
        data['installed'] = data['installed'].fuse(Part.makeBox(5, 30, 5, App.Vector(18, 0, -2)))
        with self.assertRaises(ValueError):
            port.verify_installation(self.config, data)
        # Missing material above the D section would be a leak through the round hole.
        data = dict(self.parts['BassPort'])
        data['installed'] = data['installed'].cut(Part.makeBox(2, 10, 0.5, App.Vector(-1, -5, 18)))
        with self.assertRaises(ValueError):
            port.verify_installation(self.config, data)

    def test_exact_screw_passages_and_exterior_conical_head_seats(self):
        t = self.config['trial']
        m = self.config['measured']
        centers = port.screw_centers(self.config)
        self.assertEqual(len(centers), 4)
        self.assertEqual(t['screw_hole_diameter'], 4)
        self.assertEqual(m['screw_head_diameter'], 7.5)
        self.assertEqual(m['screw_head_height'], 2.5)
        self.assertEqual(t['countersink_depth'], 3)
        for index, (x, z) in enumerate(centers):
            self.assertAlmostEqual(math.hypot(x, z), 25)
            next_x, next_z = centers[(index + 1) % 4]
            self.assertAlmostEqual(x * next_x + z * next_z, 0, places=6)
            self.assertGreater(math.hypot(x, z) - 3.75, 19)
            for data in self.parts.values():
                shape = data['installed']
                bore = Part.makeCylinder(2, 6, App.Vector(x, -5, z), App.Vector(0, 1, 0))
                head = Part.makeCone(3.75, 2, 3, App.Vector(x, -4, z), App.Vector(0, 1, 0))
                self.assertLess(shape.common(bore.fuse(head)).Volume, 1e-6)
                actual_head = Part.makeCone(3.75, 1.9, 2.5, App.Vector(x, -4, z), App.Vector(0, 1, 0))
                self.assertLess(shape.common(actual_head).Volume, 1e-6)
                # Check both sides of the actual sloped wall at several depths,
                # and that the final 1 mm retains a cylindrical Ø4 passage.
                for y, radius in [(-3.99, 3.75 - .01 * 1.75 / 3),
                                  (-3, 3.75 - 1.75 / 3), (-2, 3.75 - 3.5 / 3),
                                  (-.9, 2), (-.01, 2)]:
                    for angle in range(0, 360, 45):
                        a = math.radians(angle)
                        for offset, material in [(-.02, False), (.02, True)]:
                            point = App.Vector(x + (radius + offset) * math.cos(a), y,
                                               z + (radius + offset) * math.sin(a))
                            self.assertEqual(shape.isInside(point, 1e-6, False), material)

    def test_print_orientation_and_single_open_airway(self):
        for name, data in self.parts.items():
            installed, printed = data['installed'], data['printable']
            self.assertTrue(printed.isValid())
            self.assertEqual(len(printed.Solids), 1)
            box = printed.optimalBoundingBox(False)
            self.assertAlmostEqual(box.ZMin, 0)
            for actual, expected in zip(data['print_size_mm'], [60, 60, 90 if name == 'BassPort' else 24]):
                self.assertAlmostEqual(actual, expected, places=5)
            self.assertAlmostEqual(installed.Volume, printed.Volume)
            bore = port.airway(self.config, data['insertion_length_mm'])
            self.assertLess(installed.common(bore).Volume, 1e-6)
            # A flat annular exterior face remains available on the print bed.
            contact = port.end_face(installed, -4)
            expected = math.pi * 30**2 - data['exterior_mouth_area_mm2'] - 4 * math.pi * 3.75**2
            self.assertAlmostEqual(contact.Area, expected, places=5)

    def test_complete_round_collar_and_D_start_at_measured_inner_face(self):
        c, d = self.config, port.datums(self.config)
        self.assertEqual(c['measured']['panel_thickness'], 12)
        for data in self.parts.values():
            shape = data['installed']
            filled = shape.fuse(port.airway(c, data['insertion_length_mm']))
            collar = filled.common(Part.makeBox(100, 12, 100, App.Vector(-50, 0, -50)))
            wanted = Part.makeCylinder(d['radius'], 12, App.Vector(), App.Vector(0, 1, 0))
            self.assertLess(max(collar.cut(wanted).Volume, wanted.cut(collar).Volume), 1e-5)
            for y in (0.1, 6, 11.9):
                self.assertTrue(shape.isInside(App.Vector(0, y, 18.7), 1e-6, False))
            self.assertFalse(shape.isInside(App.Vector(0, 12.01, 18.7), 1e-6, False))
            # The transition stays in the 3 mm inward offset of the round collar.
            void = wanted.cut(shape)
            core = Part.makeCylinder(d['radius'] - 3, 12, App.Vector(), App.Vector(0, 1, 0))
            self.assertLess(void.cut(core).Volume, 1e-5)

    def test_airway_contraction_has_no_blocking_step(self):
        shape = self.parts['BassPort']['installed']
        areas = []
        for y in (0.01, 1, 3, 6, 9, 11.99):
            blank = Part.makeCylinder(19, .01, App.Vector(0, y, 0), App.Vector(0, 1, 0))
            areas.append(blank.cut(shape).Volume / .01)
        self.assertTrue(all(a > b for a, b in zip(areas, areas[1:])))
        self.assertGreater(areas[-1], self.metrics['bore_area_mm2'])
        self.assertLess(areas[0], math.pi * 16**2)

    def test_both_mouths_have_R1p5_without_outer_envelope_growth(self):
        c, d = self.config, port.datums(self.config)
        for data in self.parts.values():
            shape, length = data['installed'], data['insertion_length_mm']
            radius = c['trial']['mouth_fillet_radius']
            self.assertEqual(radius, 1.5)
            self.assertAlmostEqual(data['exterior_mouth_area_mm2'], math.pi * (16 + radius)**2, places=5)
            self.assertGreater(data['interior_mouth_area_mm2'], self.metrics['bore_area_mm2'])
            exterior_curves = [face for face in shape.Faces
                               if abs(getattr(face.Surface, 'MinorRadius', 0) - radius) < 1e-6
                               and face.optimalBoundingBox(False).YMin < -3.9]
            interior_curves = [face for face in shape.Faces
                               if abs(getattr(face.Surface, 'Radius', 0) - radius) < 1e-6
                               and face.optimalBoundingBox(False).YMax > length - 0.1]
            self.assertTrue(exterior_curves)
            self.assertGreaterEqual(len(interior_curves), 2)
            # Mouth rounds remove material inward; they cannot grow the collar,
            # the D envelope, the base, or the overall length.
            envelope = Part.makeCylinder(30, 4, App.Vector(0, -4, 0), App.Vector(0, 1, 0)).fuse(
                Part.makeCylinder(d['radius'], 12, App.Vector(), App.Vector(0, 1, 0))).fuse(
                port.profile_prism(c, length - 12, 12))
            self.assertLess(shape.cut(envelope).Volume, 1e-5)

    def test_invalid_fit_and_screw_parameters_fail(self):
        for section, key, value in [('measured', 'tube_outer_height', 6),
                                     ('measured', 'wall_thickness', 13),
                                     ('measured', 'tube_outer_diameter', 39),
                                     ('trial', 'countersink_depth', 4),
                                     ('measured', 'screw_head_diameter', 10),
                                     ('trial', 'screw_hole_diameter', 3.7),
                                     ('trial', 'clock10_radial_relief', 17),
                                     ('trial', 'base_diameter', 38),
                                     ('trial', 'coupon_total_length', 12),
                                     ('trial', 'screw_count', 3),
                                     ('trial', 'screw_pitch_diameter', 40),
                                     ('trial', 'screw_pitch_diameter', 60),
                                     ('trial', 'screw_start_angle_deg', float('nan')),
                                     ('trial', 'printer_volume', [50, 256, 256]),
                                     ('trial', 'total_length', float('nan'))]:
            config = copy.deepcopy(self.config)
            config[section][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                port.build(config)
        for key, value in [('mouth_fillet_radius', 2), ('entrance_transition_start_y', -4)]:
            config = copy.deepcopy(self.config)
            config['trial'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                port.build(config)

    def test_length_estimate_scales_effective_length_at_equal_net_volume(self):
        estimate = self.metrics['length_estimate']
        self.assertAlmostEqual(estimate['area_ratio'], self.metrics['bore_area_mm2'] / (math.pi * 16**2))
        self.assertAlmostEqual(estimate['estimated_physical_length_mm'], 78.29904299, places=6)
        self.assertEqual(estimate['selected_physical_length_mm'], 90)
        self.assertEqual(self.parts['BassPort']['insertion_length_mm'], 86)
        self.assertEqual(self.parts['BassPort']['chamber_protrusion_mm'], 74)
        self.assertFalse(self.metrics['constant_section_length_estimate_applies_to_current_airway'])
        self.assertFalse(self.metrics['current_acoustic_tuning_verified'])

    def test_saved_exports_hashes_visibility_and_parameters(self):
        report = json.loads((port.OUTPUT / 'Bass-port-report.json').read_text())
        self.assertEqual(report['parameters'], self.config)
        self.assertEqual(port.verify_exports(port.OUTPUT, self.config, self.parts), report['validation'])
        self.assertEqual(report['source_sha256'], hashlib.sha256(Path(port.__file__).read_bytes()).hexdigest())
        for name, stem in port.STEMS.items():
            with ZipFile(port.OUTPUT / (stem + '.FCStd')) as archive:
                gui = ET.fromstring(archive.read('GuiDocument.xml'))
                self.assertEqual(len(gui.findall('.//ViewProvider')), 1)
                provider = gui.find(f'.//ViewProvider[@name="{name}"]')
                self.assertEqual(provider.find('Properties/Property[@name="Visibility"]/Bool').get('value'), 'true')
                self.assertIn('Camera', archive.read('GuiDocument.xml').decode())
        for line in (port.OUTPUT / 'SHA256SUMS').read_text().splitlines():
            digest, filename = line.split('  ', 1)
            self.assertEqual(hashlib.sha256((port.OUTPUT / filename).read_bytes()).hexdigest(), digest)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'bass-port'
            shutil.copytree(port.OUTPUT, output)
            with ZipFile(port.package(output)) as archive:
                self.assertIsNone(archive.testzip())
                for line in archive.read('bass-port/SHA256SUMS').decode().splitlines():
                    digest, filename = line.split('  ', 1)
                    self.assertEqual(hashlib.sha256(archive.read('bass-port/' + filename)).hexdigest(), digest)

    def test_headless_export_rejected(self):
        if App.GuiUp:
            self.skipTest('Headless boundary requires a headless process')
        with self.assertRaisesRegex(RuntimeError, 'GUI'):
            port.export()


if __name__ == '__main__':
    unittest.main()
