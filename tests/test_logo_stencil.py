"""Printability, registration and lettering checks for the removable tooling."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import FreeCAD as App
import MeshPart

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_logo_stencil as stencil
import fascia


class LogoStencilTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = json.loads((ROOT / 'cad/parameters.json').read_text())
        cls.doc = App.newDocument('StencilTest')
        cls.installed, cls.printable, cls.data = stencil.build(cls.p, cls.doc)

    @classmethod
    def tearDownClass(cls):
        App.closeDocument(cls.doc.Name)

    def test_counter_islands_are_connected_and_mesh_is_closed(self):
        self.assertTrue(self.installed.isValid())
        self.assertEqual(len(self.installed.Solids), 1)
        self.assertEqual([item['letter'] for item in self.data['bridges']], ['A', 'r'])
        mesh = MeshPart.meshFromShape(Shape=self.printable, LinearDeflection=0.03,
                                      AngularDeflection=0.15, Relative=False)
        self.assertTrue(mesh.isSolid())
        self.assertEqual(mesh.countComponents(), 1)

    def test_two_stops_touch_bare_fascia_without_penetrating_it(self):
        metal, _ = fascia.installation(self.p)
        origin = self.data['local_origin_in_assembly_mm']
        metal.rotate(App.Vector(), App.Vector(1, 0, 0), -90)
        metal.translate(App.Vector(-origin[0], -origin[2], 0))
        self.assertLess(self.installed.common(metal).Volume, 1e-6)
        # The two locating faces coincide with the top and right end of the metal.
        for point in ((30, 30, -2), (107.5, 10, -2)):
            vertex = App.Vector(*point)
            self.assertTrue(metal.isInside(vertex, 1e-6, True))
            self.assertTrue(self.installed.isInside(vertex, 1e-6, True))

    def test_working_face_is_flat_on_bed_and_rotation_preserves_glyphs(self):
        bounds = self.printable.optimalBoundingBox(False)
        for actual, expected in zip((bounds.XLength, bounds.YLength, bounds.ZLength),
                                    (109.5, 32, 6.5)):
            self.assertAlmostEqual(actual, expected, places=6)
        self.assertAlmostEqual(bounds.ZMin, 0, places=6)
        restored = self.printable.copy()
        restored.translate(App.Vector(0, -32, -stencil.FACE_THICKNESS))
        restored.rotate(App.Vector(), App.Vector(1, 0, 0), -180)
        self.assertLess(restored.cut(self.installed).Volume, 1e-6)
        self.assertLess(self.installed.cut(restored).Volume, 1e-6)

    def test_lettering_has_material_margins_and_no_temporary_text_object(self):
        x0, y0, x1, y1 = self.data['text_bounds_mm']
        self.assertGreater(x0, 3)
        self.assertGreater(y0, 3)
        self.assertLess(x1, self.data['local_fascia_right_mm'] - 3)
        self.assertLess(y1, self.data['local_fascia_top_mm'] - 3)
        self.assertEqual(self.doc.Objects, [])

    @unittest.skipIf(App.GuiUp, 'Headless export boundary only')
    def test_headless_export_cannot_overwrite_visible_cad_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'exports'
            with self.assertRaisesRegex(RuntimeError, 'FreeCAD GUI'):
                stencil.export(output)
            self.assertFalse(output.exists())

    def test_saved_tool_has_visible_gui_provider_and_camera(self):
        with ZipFile(ROOT / 'output/3d-print/Ariel-stencil.FCStd') as archive:
            self.assertIn('GuiDocument.xml', archive.namelist())
            gui = ET.fromstring(archive.read('GuiDocument.xml'))
        provider = gui.find('.//ViewProvider[@name="ArielStencil"]')
        self.assertIsNotNone(provider)
        visibility = provider.find('Properties/Property[@name="Visibility"]/Bool')
        self.assertEqual(visibility.get('value'), 'true')
        self.assertTrue(gui.find('Camera').get('settings'))


if __name__ == '__main__':
    unittest.main()
