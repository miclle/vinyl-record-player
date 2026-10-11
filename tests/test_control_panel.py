"""Check saved panel dimensions, requested bore schedule and export topology."""
import copy
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import FreeCAD as App
import Part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_control_panel as panel


class ControlPanelTests(unittest.TestCase):
    def test_saved_level_indicators_clear_14_mm_knob_caps_and_right_edge(self):
        doc = App.openDocument(str(panel.OUTPUT / 'Control-panel.FCStd'))
        try:
            ink = doc.Markings.Shape
            self.assertEqual(len(ink.Solids), 62)
            for y in (50, 72, 94):
                ramp = ink.common(Part.makeBox(12, 4, 0.4, App.Vector(54.5,170-y-2,3.5)))
                self.assertEqual(len(ramp.Solids), 1)
                bounds = ramp.optimalBoundingBox(False)
                for actual, expected in zip((bounds.XMin,bounds.XMax,bounds.YMin,bounds.YMax,bounds.ZMin,bounds.ZMax),
                                            (55,66,170-y-1.5,170-y+1.5,3.5,3.9)):
                    self.assertAlmostEqual(actual,expected,places=5)
                self.assertAlmostEqual(ramp.Volume,11*3*0.4/2,places=5)
                cap = Part.makeCylinder(7,1,App.Vector(45,170-y,3.5))
                self.assertGreaterEqual(ramp.distToShape(cap)[0],3)
                self.assertAlmostEqual(70-bounds.XMax,4,places=5)
                # The narrow end is on the left; the wide end is on the right.
                self.assertFalse(ink.isInside(App.Vector(55.1,170-y+1,3.7),1e-6,False))
                self.assertTrue(ink.isInside(App.Vector(65.9,170-y+1,3.7),1e-6,False))
        finally:
            App.closeDocument(doc.Name)

    def test_saved_requested_dimensions_and_hole_schedule(self):
        doc = App.openDocument(str(panel.OUTPUT / 'Control-panel.FCStd'))
        try:
            shape = doc.ControlPanel.Shape
            box = shape.optimalBoundingBox(False)
            for actual, target in zip((box.XLength, box.YLength, box.ZLength), (70, 170, 3.5)):
                self.assertAlmostEqual(actual, target, places=6)
            # Independent drawing-coordinate acceptance schedule, not read from generator.
            schedule = [(15.3, 20, 7.5), (25, 20, 3.5), (45, 20, 7.5),
                        (45, 50, 7.5), (45, 72, 7.5), (45, 94, 7.5), (45, 112, 3.5),
                        (9.5, 6, 3.5), (60.5, 6, 3.5), (9.5, 164, 3.5), (60.5, 164, 3.5)]
            cylinders = [f.Surface for f in shape.Faces if isinstance(f.Surface, Part.Cylinder)]
            self.assertEqual(len(cylinders), 11)
            for x, y, diameter in schedule:
                center = App.Vector(x, 170 - y, -1)
                bore = Part.makeCylinder(diameter / 2 - 0.001, 8.5, center)
                self.assertLess(bore.common(shape).Volume, 1e-6)
                self.assertEqual(sum(abs(s.Center.x-x) < 1e-6
                                     and abs(s.Center.y-(170-y)) < 1e-6
                                     and abs(s.Radius-diameter/2) < 1e-6
                                     for s in cylinders), 1)
                self.assertTrue(shape.isInside(App.Vector(x + diameter/2 + 0.01, 170-y, 1.75),
                                               1e-6, False))
        finally:
            App.closeDocument(doc.Name)

    def test_saved_exports_and_visibility(self):
        p = panel.load_parameters()
        result = panel.verify_exports(panel.OUTPUT, panel.build(p), p)
        self.assertTrue(result['passed'])
        with ZipFile(panel.OUTPUT / 'Control-panel.FCStd') as archive:
            xml = ET.fromstring(archive.read('GuiDocument.xml'))
            provider = xml.find('.//ViewProvider[@name="ControlPanel"]')
            self.assertIsNotNone(provider)
            markings = xml.find('.//ViewProvider[@name="Markings"]')
            self.assertIsNotNone(markings)
            self.assertEqual(markings.find('.//Property[@name="Visibility"]/Bool').get('value'), 'true')
            self.assertEqual(provider.find('.//Property[@name="Visibility"]/Bool').get('value'), 'true')

    def test_saved_flat_rear_and_full_panel_thickness(self):
        doc = App.openDocument(str(panel.OUTPUT / 'Control-panel.FCStd'))
        try:
            shape = doc.ControlPanel.Shape
            self.assertLess(shape.common(Part.makeBox(70,170,10,App.Vector(0,0,-10))).Volume,1e-6)
            rear = [face for face in shape.Faces
                    if abs(face.optimalBoundingBox(False).ZMin)<1e-6
                    and abs(face.optimalBoundingBox(False).ZMax)<1e-6]
            self.assertEqual(len(rear),1)
            self.assertEqual(len(rear[0].Wires),12)
            self.assertTrue(shape.isInside(App.Vector(3.85,60,0.01),1e-6,False))
            self.assertTrue(shape.isInside(App.Vector(30,62.5,3.49),1e-6,False))
        finally:
            App.closeDocument(doc.Name)

    def test_saved_amplifier_pcb_bottom_allowance(self):
        doc = App.openDocument(str(panel.OUTPUT / 'Control-panel.FCStd'))
        try:
            p = __import__('json').loads(doc.ControlPanel.DesignJSON)
            self.assertEqual(p['pcb_installation']['amplifier_led_center_to_bottom_mm'], 45)
            self.assertEqual(p['pcb_installation']['orientation_to_panel_deg'], 90)
            led = next(h for h in p['holes'] if h['id']=='AmplifierPowerLED')
            self.assertEqual(led['y_mm']+45, 157)
            self.assertEqual(p['height_mm']-157,13)
            self.assertEqual(p['back_rim'],{'height_mm':0,'edges':[]})
            self.assertEqual(p['mounting']['wood_window']['y_mm']+p['mounting']['wood_window']['height_mm'],148)
            self.assertFalse(p['mounting']['wood_window']['pcb_fit_confirmed'])
            self.assertTrue(doc.ControlPanel.Shape.isInside(App.Vector(45,13,1.75),1e-6,False))
            self.assertFalse(doc.ControlPanel.Shape.isInside(App.Vector(45,13,-1.5),1e-6,False))
        finally:
            App.closeDocument(doc.Name)

    def test_stl_print_datum_preserves_front_hole_pattern(self):
        import Mesh
        mesh = Mesh.Mesh(str(panel.OUTPUT / 'Control-panel.stl'))
        edge_points = [point.Vector for point in mesh.Points if abs(point.Vector.z) < 1e-5]
        for x, y, diameter in [(15.3,20,7.5),(25,20,3.5),(45,20,7.5),
                               (45,50,7.5),(45,72,7.5),(45,94,7.5),(45,112,3.5),
                               (9.5,6,3.5),(60.5,6,3.5),(9.5,164,3.5),(60.5,164,3.5)]:
            matching = [v for v in edge_points if abs(((v.x-x)**2+(v.y-(170-y))**2)**0.5-diameter/2)<1e-4]
            self.assertGreater(len(matching), 16)

    def test_saved_raised_logo_height_counters_and_attachment(self):
        doc = App.openDocument(str(panel.OUTPUT / 'Control-panel.FCStd'))
        try:
            base,ink=doc.ControlPanel.Shape,doc.Markings.Shape
            logo=ink.common(Part.makeBox(44,12,0.4,App.Vector(10.5,25,3.5)))
            self.assertEqual(len(logo.Solids),5)
            b=logo.optimalBoundingBox(False)
            for actual,expected in zip((b.XMin,b.XMax,(b.YMin+b.YMax)/2,b.ZMin,b.ZMax),
                                        (11.5,53.5,31,3.5,3.9)):
                self.assertAlmostEqual(actual,expected,delta=0.002)
            self.assertLess(base.common(ink).Volume,1e-6)
            # Every glyph must touch the plate through its complete bottom footprint.
            for letter in ink.Solids:
                lower=letter.copy();lower.translate(App.Vector(0,0,-0.4))
                self.assertAlmostEqual(lower.common(base).Volume,lower.Volume,places=5)
            for letter in sorted(logo.Solids,key=lambda v:v.CenterOfMass.x)[:2]:
                face=next(f for f in letter.Faces if abs(f.optimalBoundingBox(False).ZMax-3.5)<1e-6)
                self.assertEqual(len(face.Wires),2)
                counter=min((Part.Face(w) for w in face.Wires),key=lambda f:f.Area)
                c=counter.CenterOfMass
                self.assertFalse(ink.isInside(App.Vector(c.x,c.y,3.7),1e-6,False))
                self.assertTrue(base.isInside(App.Vector(c.x,c.y,3.49),1e-6,False))
            import Mesh
            mesh=Mesh.Mesh(str(panel.OUTPUT / 'Control-panel-markings.stl'))
            self.assertAlmostEqual(mesh.BoundBox.ZMin,3.5,places=5)
            self.assertAlmostEqual(mesh.BoundBox.ZMax,3.9,places=5)
        finally:
            App.closeDocument(doc.Name)

    def test_color_3mf_preserves_materials_and_mesh_positions(self):
        import Mesh
        ns = {'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
        with ZipFile(panel.OUTPUT / 'Control-panel-color.3mf') as archive:
            self.assertIsNone(archive.testzip())
            root = ET.fromstring(archive.read('3D/3dmodel.model'))
            config = ET.fromstring(archive.read('Metadata/model_settings.config'))
            settings = __import__('json').loads(archive.read('Metadata/project_settings.config'))
        self.assertEqual(settings['filament_colour'], ['#000000', '#FFFFFF'])
        parts = config.findall('object/part')
        self.assertEqual([part.get('id') for part in parts], ['2','3'])
        self.assertEqual([part.find('metadata[@key="extruder"]').get('value') for part in parts], ['1','2'])
        self.assertEqual(root.get('unit'), 'millimeter')
        materials = root.findall('m:resources/m:basematerials/m:base',ns)
        self.assertEqual([m.get('displaycolor') for m in materials], ['#000000FF','#FFFFFFFF'])
        objects = root.findall('m:resources/m:object',ns)
        self.assertEqual(len(objects),3)
        self.assertEqual(root.find('m:build/m:item',ns).get('objectid'),'4')
        self.assertEqual([c.get('objectid') for c in objects[2].findall('m:components/m:component',ns)],['2','3'])
        for index, obj in enumerate(objects[:2]):
            self.assertIsNone(obj.get('pid'))
            self.assertIsNone(obj.get('pindex'))
            self.assertTrue(all(t.get('pid') is None and t.get('paint_color') is None
                for t in obj.findall('m:mesh/m:triangles/m:triangle',ns)))
            vertices = [App.Vector(float(v.get('x')),float(v.get('y')),float(v.get('z')))
                        for v in obj.findall('m:mesh/m:vertices/m:vertex',ns)]
            facets = [tuple(int(t.get(k)) for k in ('v1','v2','v3'))
                      for t in obj.findall('m:mesh/m:triangles/m:triangle',ns)]
            mesh = Mesh.Mesh((vertices,facets))
            filename = 'Control-panel.stl' if index==0 else 'Control-panel-markings.stl'
            stl = Mesh.Mesh(str(panel.OUTPUT / filename))
            self.assertEqual(mesh.CountFacets,stl.CountFacets)
            self.assertTrue(mesh.isSolid())
            self.assertEqual(mesh.countComponents(),stl.countComponents())
            self.assertAlmostEqual(panel.mesh_volume(mesh),panel.mesh_volume(stl),places=3)
            for v,w in zip(mesh.BoundBox.getPoint(0),stl.BoundBox.getPoint(0)):
                self.assertAlmostEqual(v,w,places=5)
            self.assertLess(mesh.BoundBox.ZMax,3.90001)
            if index==1:
                self.assertAlmostEqual(mesh.BoundBox.ZMin,3.5,places=5)
                self.assertAlmostEqual(mesh.BoundBox.ZMax,3.9,places=5)

    def test_holes_reaching_edges_or_each_other_are_rejected(self):
        p = copy.deepcopy(panel.load_parameters())
        p['holes'][0]['x_mm'] = 3.4
        with self.assertRaisesRegex(ValueError, 'reaches a panel edge'):
            panel.build(p)
        p = copy.deepcopy(panel.load_parameters())
        p['holes'][1]['x_mm'] = 12
        with self.assertRaisesRegex(ValueError, 'boundaries must remain separate'):
            panel.build(p)

    def test_functional_font_is_plain_and_logo_font_is_preserved(self):
        p=panel.load_parameters()
        self.assertEqual(p['front_logo']['font'],'references/fonts/sigmar-one/SigmarOne-Regular.ttf')
        self.assertEqual(p['front_markings']['font'],'references/fonts/noto-sans/NotoSans-Bold.ttf')
        self.assertTrue((ROOT/p['front_markings']['font']).is_file())
        self.assertTrue((ROOT/'references/fonts/noto-sans/OFL.txt').is_file())
        self.assertGreaterEqual(min(l['cap_height_mm'] for l in p['front_markings']['labels']),2.6)


if __name__ == '__main__':
    unittest.main()
