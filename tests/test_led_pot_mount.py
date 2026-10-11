"""Separate flat plate and knob, straight wood opening and saved print solids."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import FreeCAD as App
import Part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import build_led_pot_mount as controls


class LEDPotControlsTests(unittest.TestCase):
    def setUp(self):
        self.p = controls.load_parameters()

    def test_plate_is_flat_without_recess_or_boss(self):
        shape = controls.build_plate(self.p)
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Solids), 1)
        b = shape.optimalBoundingBox(False)
        self.assertEqual((b.XLength, b.YLength, b.ZLength, b.ZMin), (22, 36, 2, 0))
        self.assertEqual(controls.layout(self.p)['screw_centers_mm'], [(0, -14), (0, 14)])
        self.assertAlmostEqual(controls.layout(self.p)['side_clearance_mm'], 4)
        for z in (0.01, 1, 1.99):
            self.assertFalse(shape.isInside(App.Vector(0, 0, z), 1e-7, False))
            self.assertTrue(shape.isInside(App.Vector(5, 0, z), 1e-7, False))
        for x, y in controls.layout(self.p)['screw_centers_mm']:
            self.assertLess(shape.common(Part.makeCylinder(1.699, 2, App.Vector(x, y, 0))).Volume, 1e-7)

    def test_knob_blind_bore_stem_wall_and_print_orientation(self):
        shape = controls.build_knob(self.p)
        b = shape.optimalBoundingBox(False)
        self.assertEqual(len(shape.Solids), 1)
        for actual, expected in zip((b.XLength, b.YLength, b.ZLength, b.ZMin), (20, 20, 12.2, 0)):
            self.assertAlmostEqual(actual, expected)
        self.assertTrue(shape.isInside(App.Vector(0, 0, 3.89), 1e-7, False))
        self.assertFalse(shape.isInside(App.Vector(0, 0, 3.91), 1e-7, False))
        self.assertFalse(shape.isInside(App.Vector(0, 0, 12.19), 1e-7, False))
        self.assertTrue(shape.isInside(App.Vector(4, 0, 10), 1e-7, False))
        self.assertFalse(shape.isInside(App.Vector(7, 0, 5.1), 1e-7, False))
        self.assertAlmostEqual(controls.layout(self.p)['bore_roof_mm'], 3.9)

    def test_constant_twelve_mm_wood_bore_and_measured_nut(self):
        wood = controls.fixtures(self.p)['Wood']
        d = controls.layout(self.p)
        self.assertEqual(self.p['back_panel']['opening_diameter_mm'], 12)
        self.assertEqual(self.p['potentiometer']['nut_max_diameter_mm'], 11)
        for depth in (0.1, 3, 6, 9, 11.9):
            z = d['wood_inner_z_mm']+depth
            for angle in range(0, 360, 45):
                a = math.radians(angle)
                self.assertFalse(wood.isInside(App.Vector(5.99*math.cos(a), 5.99*math.sin(a), z), 1e-7, False))
                self.assertTrue(wood.isInside(App.Vector(6.01*math.cos(a), 6.01*math.sin(a), z), 1e-7, False))
        self.assertTrue(controls.verify_fit(self.p)['nominal_fixture_clear'])

    def test_measured_height_chain_and_parameter_changes(self):
        d = controls.layout(self.p)
        self.assertAlmostEqual(d['shaft_tip_beyond_wood_mm'], 1.3)
        self.assertAlmostEqual(d['stem_length_mm'], 7.2)
        self.assertAlmostEqual(d['knob_projection_mm'], 5.5)
        self.assertAlmostEqual(d['knob_bushing_gap_mm'], 0.5)
        self.assertEqual(self.p['potentiometer']['shaft_profile'], 'splined')
        self.assertAlmostEqual(self.p['potentiometer']['shaft_diameter_mm'], 5.9)
        self.assertAlmostEqual(d['shaft_bore_diametral_clearance_min_mm'], 0.1)
        self.assertAlmostEqual(d['shaft_bore_diametral_clearance_max_mm'], 0.2)
        self.assertFalse(controls.verify_fit(self.p)['spline_geometry_modeled'])
        for diameter in (5.8, 5.9):
            p = deepcopy(self.p)
            p['potentiometer']['shaft_diameter_mm'] = diameter
            self.assertTrue(controls.verify_fit(p)['nominal_fixture_clear'])
            self.assertAlmostEqual(controls.fixtures(p)['Shaft'].optimalBoundingBox(False).XLength, diameter)
        for section, key, value, expected_length in (
                ('knob', 'shaft_engagement_mm', 7, 6.2),
                ('back_panel', 'thickness_mm', 14, 9.2),
                ('plate', 'thickness_mm', 1.8, 7.0)):
            with self.subTest(key=key):
                p = deepcopy(self.p)
                p[section][key] = value
                self.assertAlmostEqual(controls.layout(p)['stem_length_mm'], expected_length)
                self.assertAlmostEqual(controls.layout(p)['knob_projection_mm'], 5.5)
                self.assertTrue(controls.verify_fit(p)['nominal_fixture_clear'])

    def test_d_shaft_profile_survives_print_to_install_rotation(self):
        p = deepcopy(self.p)
        p['potentiometer']['shaft_profile'] = 'd'
        self.assertTrue(controls.build_knob(p).isInside(App.Vector(2.5, 0, 10), 1e-7, False))
        self.assertFalse(controls.build_knob(self.p).isInside(App.Vector(2.5, 0, 10), 1e-7, False))
        self.assertTrue(controls.verify_fit(p)['nominal_fixture_clear'])
        self.assertFalse(controls.verify_fit(p)['actual_shaft_fit_and_torque_verified'])

    def test_optional_stop_lug_and_invalid_fit_rejected(self):
        p = deepcopy(self.p)
        p['anti_rotation']['enabled'] = True
        self.assertFalse(controls.build_plate(p).isInside(App.Vector(0, 8, 1), 1e-7, False))
        self.assertTrue(controls.build_plate(self.p).isInside(App.Vector(0, 8, 1), 1e-7, False))
        changes = [('knob', 'shaft_engagement_mm', 9), ('knob', 'stem_diameter_mm', 12),
                   ('knob', 'bore_diameter_mm', 8), ('knob', 'bore_tip_clearance_mm', 4.5),
                   ('potentiometer', 'thread_length_mm', 4), ('potentiometer', 'washer_outer_diameter_mm', 12),
                   ('back_panel', 'opening_diameter_mm', 11), ('plate', 'wood_pilot_depth_mm', 12),
                   ('plate', 'screw_pitch_y_mm', 34), ('installation', 'available_width_mm', 21),
                   ('potentiometer', 'shaft_profile', 'knurled')]
        for section, key, value in changes:
            with self.subTest(key=key):
                p = deepcopy(self.p)
                p[section][key] = value
                with self.assertRaises(ValueError):
                    controls.layout(p)

    def test_separate_saved_exports_and_visibility(self):
        result = controls.verify_exports()
        self.assertTrue(result['passed'])
        self.assertEqual(set(result['parts']), {'Plate', 'Knob'})
        for name, stem in controls.PARTS.items():
            self.assertEqual(result['parts'][name]['mesh_components'], 1)
            with ZipFile(controls.OUTPUT/(stem+'.FCStd')) as archive:
                root = ET.fromstring(archive.read('GuiDocument.xml'))
                visible = root.findall('.//Property[@name="Visibility"]/Bool')
                self.assertEqual(len(visible), 1)
                self.assertEqual(visible[0].get('value'), 'true')

    def test_headless_export_boundary_and_main_files_untouched(self):
        if App.GuiUp:
            self.skipTest('Console export guard requires headless Python')
        files = [ROOT/'cad'/name for name in ('parameters.json', 'record-player.FCStd', 'record-player.step')]
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
        with self.assertRaises(RuntimeError):
            controls.export()
        controls.build_plate(self.p)
        controls.build_knob(self.p)
        self.assertEqual(before, [hashlib.sha256(path.read_bytes()).hexdigest() for path in files])


if __name__ == '__main__':
    unittest.main()
