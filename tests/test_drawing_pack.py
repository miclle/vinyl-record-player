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
    def test_saved_geometry_coverage_split_panels_and_slope_thickness(self):
        spec = importlib.util.find_spec('drawing_data')
        self.assertIsNotNone(spec, 'drawing_data exporter is not implemented')
        import drawing_data
        paths = list((ROOT / 'cad').glob('*.FCStd'))
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        data = drawing_data.collect(ROOT, project=False)
        cards = {c['key']: c for c in data['cards']}
        self.assertEqual(data['coverage']['baseline_missing'], [])
        self.assertEqual(data['coverage']['study_missing'], [])
        self.assertEqual(data['coverage']['baseline_count'], 68)
        self.assertEqual(cards['Foot0']['size_mm'], [30.0, 30.0, 43.0])
        self.assertEqual(cards['FootMount0']['size_mm'], [37.0, 37.0, 17.0])
        self.assertEqual(len(cards['Bottom']['holes']), 5)
        self.assertEqual(len(cards['Back']['holes']), 4)
        self.assertEqual(cards['ACInlet']['size_mm'], [58.0, 30.66, 49.0])
        self.assertEqual(cards['Bottom']['size_mm'], [426.0, 350.0, 12.0])
        self.assertEqual(cards['AcousticRear:1']['size_mm'], [117.0, 8.0, 90.0])
        self.assertEqual(cards['AcousticRear:2']['size_mm'], [117.0, 8.0, 90.0])
        self.assertEqual(cards['RearSupport:1']['size_mm'], [109.0, 30.0, 8.0])
        self.assertEqual(cards['Baffle']['thickness_mm'], 8.0)
        self.assertEqual(cards['Baffle']['stock_mm'], [426.0, 98.0, 8.0])
        self.assertEqual(cards['Slat01']['stock_mm'], [426.0, 7.0, 3.0])
        self.assertEqual(cards['DustCover']['thickness_mm'], 3.0)
        self.assertIsNone(cards['KitCurvedArm']['thickness_mm'])
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})

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
            for name in ('parameters.json','selected-mechanism.json',
                         'lumi-three-driver.FCStd','lumi-selected-mechanism-fit.FCStd'):
                shutil.copy2(ROOT/'cad'/name,root/'cad'/name)
            before=set(App.listDocuments())
            for name,key in [('parameters.json','wall'),('selected-mechanism.json','nominal_width')]:
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
