"""Drawing data must cover every physical feature without altering the CAD."""
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))


class DrawingPackTests(unittest.TestCase):
    def test_nondefault_hinge_notes_match_saved_geometry_and_hole_sheets(self):
        from unittest.mock import patch
        import build_model
        import drawing_data
        import Part

        p=json.loads((ROOT/'cad/parameters.json').read_text())
        p['hinges'].update(wood_pilot_depth_assumption=7,
                           wood_pilot_diameter_assumption=3.2,
                           backing_thickness_assumption=3,
                           plate_height_assumption=20,
                           cover_hole_diameter_assumption=5.8)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'cad').mkdir()
            (root/'cad/parameters.json').write_text(json.dumps(p))
            (root / 'cad/mechanism.json').write_bytes((ROOT / 'cad/mechanism.json').read_bytes())
            shutil.copy2(ROOT/'cad/mechanism.json',root/'cad/mechanism.json')
            with patch.object(build_model,'ROOT',root):
                doc,_,_=build_model.deliver()
            App.closeDocument(doc.Name)
            saved=App.openDocument(str(root/'cad/record-player.FCStd'))
            try:
                from assembly_pose import set_cover_angle
                set_cover_angle(saved,p,0)
                self.assertEqual(saved.HingeBacking0.Shape.optimalBoundingBox(False).YLength,3)
                self.assertEqual(saved.HingeBacking0.Shape.optimalBoundingBox(False).ZLength,20)
                self.assertIn('3 mm 铝板',saved.HingeBacking0.MaterialNote)
                self.assertIn('Ø5.8',saved.DustCover.MaterialNote)
                # The new pilot ends at Y=343 and retains wood in front of it.
                probe=Part.makeCylinder(1.59,6.98,App.Vector(83,343.01,130),App.Vector(0,1,0))
                self.assertLess(saved.Back.Shape.common(probe).Volume,1e-6)
                self.assertTrue(saved.Back.Shape.isInside(App.Vector(83,342.8,130),1e-6,False))
            finally:
                App.closeDocument(saved.Name)
            data=drawing_data.collect(root,project=False)
        cards={c['key']:c for c in data['cards']}
        sheets={s['key']:s for s in data['hole_sheets']}
        self.assertIn('4×Ø3.2 深7', ' '.join(cards['Back']['notes']))
        self.assertIn('保留5 mm木厚', ' '.join(cards['Back']['notes']))
        self.assertIn('3 mm内压板', ' '.join(cards['HingePin0']['notes']))
        self.assertEqual(cards['HingeBacking0']['thickness_mm'],3)
        self.assertEqual({h['depth_mm'] for h in sheets['Back']['holes'] if h['id'].startswith('J')},{7})
        self.assertEqual({h['diameter_mm'] for h in sheets['DustCover']['holes']},{5.8})
        notes=' '.join(sheets['DustCover']['notes'])
        self.assertIn('内侧3 mm压板',notes)
        self.assertIn('外廓51×20',notes)
        self.assertIn('厚度分别为2/3',notes)
        self.assertIn('(8.5,10)/(42.5,10)',notes)

    def test_saved_geometry_coverage_split_panels_and_slope_thickness(self):
        spec = importlib.util.find_spec('drawing_data')
        self.assertIsNotNone(spec, 'drawing_data exporter is not implemented')
        import drawing_data
        paths = list((ROOT / 'cad').glob('*.FCStd'))
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        data = drawing_data.collect(ROOT, project=False)
        cards = {c['key']: c for c in data['cards']}
        self.assertEqual(data['coverage']['missing'], [])
        self.assertEqual(data['coverage']['physical_count'], 65)
        self.assertEqual(data['coverage']['reference_count'], 16)
        self.assertEqual(set(data['sources']), {'record-player.FCStd'})
        self.assertNotIn('LowerRail', cards)
        self.assertEqual(cards['GrilleCloth']['drawing_code'], 'A-P03')
        self.assertEqual(cards['GrilleCloth']['drawing_column'], 1)
        self.assertEqual(cards['Slat01']['drawing_code'], 'A-P04')
        self.assertEqual(cards['Foot0']['drawing_code'], 'A-P07')
        self.assertEqual(cards['FootMount0']['drawing_code'], 'A-P07')
        self.assertEqual(cards['Foot0']['size_mm'], [30.0, 30.0, 43.0])
        self.assertEqual(cards['FootMount0']['size_mm'], [37.0, 37.0, 17.0])
        self.assertEqual(len(cards['Bottom']['holes']), 5)
        self.assertEqual(len(cards['Back']['holes']), 4)
        self.assertEqual(cards['ACInlet']['size_mm'], [58.0, 30.66, 49.0])
        self.assertEqual(cards['Bottom']['size_mm'], [426.0, 350.0, 12.0])
        self.assertEqual(cards['Fascia']['size_mm'], [425.0, 30.0, 30.0])
        self.assertEqual(cards['Fascia']['thickness_mm'], 5.0)
        self.assertEqual(cards['AcousticRoof']['origin_mm'][1], 5.2)
        self.assertIn('深 3.7', ' '.join(cards['AcousticRoof']['notes']))
        self.assertEqual(cards['AcousticRear:1']['size_mm'], [117.0, 8.0, 90.0])
        self.assertEqual(cards['AcousticRear:2']['size_mm'], [117.0, 8.0, 90.0])
        self.assertEqual(cards['RearSupport:1']['size_mm'], [109.0, 30.0, 8.0])
        self.assertEqual(cards['Baffle']['thickness_mm'], 8.0)
        self.assertEqual(cards['Baffle']['stock_mm'], [426.0, 98.0, 8.0])
        self.assertEqual(cards['Slat01']['stock_mm'], [426.0, 7.0, 3.0])
        self.assertEqual(cards['DustCover']['thickness_mm'], 3.0)
        self.assertIsNone(cards['KitCurvedArm']['thickness_mm'])
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})

    def test_hole_sheets_match_saved_panel_geometry_and_keep_sources_unchanged(self):
        import drawing_data
        params = json.loads((ROOT / 'cad/parameters.json').read_text())
        paths = list((ROOT / 'cad').glob('*.FCStd'))
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        data = drawing_data.collect(ROOT, project=False)
        self.assertIn('hole_sheets', data)
        sheets = {s['key']: s for s in data['hole_sheets']}
        self.assertEqual(set(sheets), {'Bottom', 'Back', 'Baffle', 'AcousticRoof', 'FloatingDeck', 'DustCover'})
        bottom = sheets['Bottom']
        self.assertEqual(len(bottom['holes']), 17)
        pilots = [h for h in bottom['holes'] if h['kind'] == 'blind']
        self.assertEqual(len(pilots), 12)
        self.assertEqual((pilots[0]['u_mm'], pilots[0]['v_mm']), (35, 40))
        self.assertAlmostEqual(pilots[1]['u_mm'], 14)
        self.assertAlmostEqual(pilots[1]['v_mm'], 52.124356, places=5)
        self.assertTrue(all(h['depth_mm'] == 8 and h['diameter_mm'] == 3 for h in pilots))
        baffle = sheets['Baffle']
        self.assertAlmostEqual(baffle['size_mm'][1], 94.6316, places=3)
        self.assertAlmostEqual(baffle['holes'][0]['v_mm'], 52.573111, places=5)
        self.assertEqual([h['u_mm'] for h in baffle['holes']], [68, 358])
        back = sheets['Back']['holes']
        port = next(h for h in back if h['id'] == 'H1')
        self.assertEqual((port['u_mm'], port['v_mm']), (276, 68))
        self.assertEqual(port['recess'], {'diameter_mm': 48, 'depth_mm': 3, 'face': '后侧'})
        self.assertEqual([(h['u_mm'], h['v_mm']) for h in back[2:4]], [(58, 34), (58, 74)])
        self.assertEqual(sheets['AcousticRoof']['holes'][0]['u_mm'],
                         params['platter_x'] - params['wall'])
        self.assertAlmostEqual(sheets['AcousticRoof']['holes'][0]['v_mm'], 166.8)
        self.assertIn('余厚 4.3',' '.join(sheets['AcousticRoof']['notes']))
        self.assertEqual(sheets['FloatingDeck']['holes'][0]['u_mm'],
                         params['platter_x'] - params['wall'] - params['deck_side_clearance'])
        self.assertEqual(sheets['FloatingDeck']['holes'][0]['v_mm'],
                         params['platter_y'] - params['fascia']['thickness']
                         - params['deck_front_fascia_clearance'])
        self.assertIn('baffle_section', data)
        self.assertEqual(data['baffle_section']['x_mm'], 225)
        self.assertIn('Baffle', [part['key'] for part in data['baffle_section']['parts']])
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})

    def test_nondefault_hole_coordinates_and_depths_land_in_actual_voids(self):
        import math
        from unittest.mock import patch
        import Part
        import build_model
        import drawing_data
        from drawing_details import panel_details
        p=json.loads((ROOT/'cad/parameters.json').read_text())
        p['front_angle']=70
        p['fullrange']['center_z']=82.5
        p['feet']['pilot_depth_assumption']=7
        p['feet']['front_y']=44
        p['ac_inlet'].update(cutout_width=48.4,cutout_height=28.4,mount_hole_diameter=4.8)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'cad').mkdir()
            (root/'cad/parameters.json').write_text(json.dumps(p))
            (root / 'cad/mechanism.json').write_bytes((ROOT / 'cad/mechanism.json').read_bytes())
            with patch.object(build_model,'ROOT',root):
                doc,_,_,_=build_model.build()
            try:
                sheets={s['key']:s for s in panel_details(doc,p,drawing_data.project_shape,True)}
                for sheet in sheets.values():
                    for actual,want in zip(sheet['projection']['size_mm'],sheet['size_mm']):
                        self.assertAlmostEqual(actual,want,places=5)
                b=doc.Bottom.Shape.optimalBoundingBox(False)
                for hole in sheets['Bottom']['holes']:
                    point=App.Vector(b.XMin+hole['u_mm'],b.YMin+hole['v_mm'],b.ZMin+0.2)
                    self.assertFalse(doc.Bottom.Shape.isInside(point,1e-6,False))
                    if hole['kind']=='blind':
                        self.assertEqual(hole['depth_mm'],7)
                        point.z=b.ZMin+hole['depth_mm']+0.2
                        self.assertTrue(doc.Bottom.Shape.isInside(point,1e-6,False))
                baffle=sheets['Baffle']
                self.assertAlmostEqual(baffle['holes'][0]['v_mm'],51.080533,places=5)
                angle=math.radians(70)
                for hole in baffle['holes']:
                    point=App.Vector(12+hole['u_mm'],16+hole['v_mm']*math.cos(angle),
                                     34.5+hole['v_mm']*math.sin(angle))
                    normal=App.Vector(0,math.sin(angle),-math.cos(angle))
                    cutter=Part.makeCylinder(hole['diameter_mm']/2-0.01,7.98,point+normal*0.01,normal)
                    self.assertLess(doc.Baffle.Shape.common(cutter).Volume,1e-6)
                    self.assertTrue(doc.Baffle.Shape.isInside(point+normal*4+App.Vector(21,0,0),1e-6,False))
                back=sheets['Back']['holes']
                self.assertEqual(back[1]['width_mm'],48.4)
                self.assertEqual(back[2]['diameter_mm'],4.8)
            finally:
                App.closeDocument(doc.Name)

    def test_projection_axes_preserve_front_and_right_dimensions(self):
        spec = importlib.util.find_spec('drawing_data')
        self.assertIsNotNone(spec, 'drawing_data exporter is not implemented')
        import Part
        import drawing_data
        shape = Part.makeBox(17, 29, 43)
        self.assertEqual(drawing_data.project_shape(shape, 'front')['size_mm'], [17.0, 43.0])
        self.assertEqual(drawing_data.project_shape(shape, 'right')['size_mm'], [29.0, 43.0])
        self.assertEqual(drawing_data.project_shape(shape, 'top')['size_mm'], [17.0, 29.0])

    def test_stale_parameter_inputs_are_rejected_and_documents_are_closed(self):
        import drawing_data
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'cad').mkdir()
            for name in ('parameters.json','mechanism.json',
                         'record-player.FCStd'):
                shutil.copy2(ROOT/'cad'/name,root/'cad'/name)
            before=set(App.listDocuments())
            for name,key in [('parameters.json','wall'),('mechanism.json','nominal_width')]:
                path=root/'cad'/name
                original=path.read_text()
                params=json.loads(original)
                params[key]+=1
                path.write_text(json.dumps(params))
                with self.assertRaisesRegex(ValueError,'snapshot differs'):
                    drawing_data.collect(root,project=False)
                self.assertEqual(set(App.listDocuments()),before)
                path.write_text(original)


if __name__ == '__main__':
    unittest.main()
