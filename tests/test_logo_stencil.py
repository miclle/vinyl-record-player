"""Printability, registration and lettering checks for the removable tooling."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import FreeCAD as App
import Mesh
import MeshPart
import Part
import Draft

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_logo_stencil as stencil
import fascia
import nameplate


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

    def test_face_up_print_pose_has_stops_on_bed_and_preserves_glyphs(self):
        bounds = self.printable.optimalBoundingBox(False)
        for actual, expected in zip((bounds.XLength, bounds.YLength, bounds.ZLength),
                                    (109.5, 32, 16.3)):
            self.assertAlmostEqual(actual, expected, places=6)
        self.assertAlmostEqual(bounds.ZMin, 0, places=6)
        restored = self.printable.copy()
        restored.translate(App.Vector(0, 0, -stencil.STOP_DEPTH))
        self.assertLess(restored.cut(self.installed).Volume, 1e-6)
        self.assertLess(self.installed.cut(restored).Volume, 1e-6)

    def test_counter_glyphs_are_clear_below_beams_and_islands_touch_metal(self):
        label = Draft.make_shapestring(nameplate.TEXT, str(nameplate.FONT),
                                       Size=self.p['fascia']['nameplate']['text_height'])
        try:
            self.doc.recompute()
            letters = label.Shape.copy()
            b = letters.optimalBoundingBox(False)
            plate = nameplate.dimensions(self.p)
            letters.translate(App.Vector((plate['width'] - b.XLength) / 2 - b.XMin,
                                          (30 - b.YLength) / 2 - b.YMin, 0))
            # Coincident-wall booleans fail on independently regenerated A splines.
            # Sample both changed glyphs at 0.5 mm, through the face and bridge gap.
            checked = 0
            beam_hits = 0
            for face in letters.Faces[:2]:
                bounds = face.optimalBoundingBox(False)
                for ix in range(int(bounds.XLength / 0.5) + 1):
                    for iy in range(int(bounds.YLength / 0.5) + 1):
                        x, y = bounds.XMin + ix * 0.5, bounds.YMin + iy * 0.5
                        if not face.isInside(App.Vector(x, y, 0), 1e-6, False):
                            continue
                        checked += 1
                        for z in (0.6, 1.3, stencil.BRIDGE_CLEARANCE - 0.001):
                            self.assertFalse(self.installed.isInside(App.Vector(x, y, z),
                                                                     1e-6, False))
                        beam_hits += self.installed.isInside(
                            App.Vector(x, y, stencil.BRIDGE_CLEARANCE + 0.5), 1e-6, False)
            self.assertGreater(checked, 1000)
            self.assertGreater(beam_hits, 20)
            for face in letters.Faces[:2]:
                island = Part.Face(next(w for w in face.Wires if not w.isSame(face.OuterWire)))
                # Clip with a box outside the spline boundary to avoid a
                # coincident-wall boolean. Verify the full bridge-gap column.
                b = island.optimalBoundingBox(False)
                clip = Part.makeBox(b.XLength + 0.02, b.YLength + 0.02, 7.998,
                                    App.Vector(b.XMin - 0.01, b.YMin - 0.01, 0.001))
                column = self.installed.common(clip)
                self.assertEqual(len(column.Solids), 1)
                self.assertAlmostEqual(column.Volume, island.Area * 7.998, delta=1e-3)
                actual = column.optimalBoundingBox(False)
                for key in ('XMin', 'XMax', 'YMin', 'YMax'):
                    self.assertAlmostEqual(getattr(actual, key), getattr(b, key), places=6)
                self.assertAlmostEqual(column.Solids[0].CenterOfMass.x, island.CenterOfMass.x, delta=1e-4)
                self.assertAlmostEqual(column.Solids[0].CenterOfMass.y, island.CenterOfMass.y, delta=1e-4)
            for bridge in self.data['bridges']:
                x0, y0, x1, y1 = bridge['beam_bounds_xy_mm']
                self.assertAlmostEqual(x1 - x0, 3)
                beam = Part.makeBox(3, y1 - y0, 3, App.Vector(x0, y0, 8))
                self.assertLess(beam.cut(self.installed).Volume, 1e-6)
                ax, ay = bridge['anchor_center_mm']
                anchor = Part.makeBox(3, 3, 11, App.Vector(ax - 1.5, ay - 1.5, 0))
                self.assertLess(anchor.cut(self.installed).Volume, 1e-6)
        finally:
            self.doc.removeObject(label.Name)

    def test_saved_exports_match_current_solid_and_closed_mesh(self):
        saved = App.openDocument(str(ROOT / 'output/3d-print/Ariel-stencil.FCStd'))
        try:
            cad = saved.getObject('ArielStencil').Shape
            step = Part.Shape()
            step.read(str(ROOT / 'output/3d-print/Ariel-stencil.step'))
            for shape in (cad, step):
                self.assertTrue(shape.isValid())
                self.assertEqual(len(shape.Solids), 1)
                self.assertLess(shape.cut(self.printable).Volume, 1e-5)
                self.assertLess(self.printable.cut(shape).Volume, 1e-5)
            mesh = Mesh.Mesh(str(ROOT / 'output/3d-print/Ariel-stencil.stl'))
            self.assertTrue(mesh.isSolid())
            self.assertEqual(mesh.countComponents(), 1)
            self.assertAlmostEqual(abs(mesh.Volume), self.printable.Volume, delta=0.5)
            data = json.loads((ROOT / 'output/3d-print/Ariel-stencil.json').read_text())
            self.assertEqual(data['print_size_mm'], self.data['print_size_mm'])
            self.assertEqual(data['bridges'], self.data['bridges'])
        finally:
            App.closeDocument(saved.Name)

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
