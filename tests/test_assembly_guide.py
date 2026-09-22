"""The guide must map the selected assembly, not the historical mechanism."""
import copy
import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import assembly_guide
import drawing_data


class AssemblyGuideTests(unittest.TestCase):
    def test_overview_targets_exist_with_one_three_or_eight_slats(self):
        data = drawing_data.collect(ROOT, project=False)
        for count in (1, 3, 8):
            with self.subTest(slat_count=count):
                changed = copy.deepcopy(data)
                for card in changed['cards']:
                    if 'Slat01' in card['ids']:
                        card['ids'] = card['ids'][:count]
                entries = assembly_guide.catalog_from_drawings(changed)
                targets = assembly_guide.overview_targets(entries)
                catalog = {e['code']: e for e in entries}
                self.assertEqual(catalog['W02']['quantity'], f'{count} 条')
                self.assertEqual(set(targets), {e['code'] for e in entries if e['page'] == 1})
                for code, (name, fraction) in targets.items():
                    self.assertIn(name, catalog[code]['ids'])
                if count == 8:
                    self.assertEqual(targets['W02'][0], 'Slat04')

    def test_selected_objects_have_unique_codes_and_current_drawing_references(self):
        paths = list((ROOT/'cad').glob('*.FCStd'))
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        data = drawing_data.collect(ROOT, project=False)
        entries = assembly_guide.catalog_from_drawings(data)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'GuideTest.FCStd'
            shutil.copy2(ROOT/'cad/lumi-selected-mechanism-fit.FCStd', path)
            doc = App.openDocument(str(path))
            try:
                self.assertEqual(assembly_guide.check_coverage(doc, entries), 61)
                with self.assertRaisesRegex(ValueError, 'coverage mismatch'):
                    assembly_guide.check_coverage(doc, entries[:-1])
                with self.assertRaisesRegex(ValueError, 'duplicate=True'):
                    assembly_guide.check_coverage(doc, entries+[copy.deepcopy(entries[0])])
            finally:
                App.closeDocument(doc.Name)
        catalog = {e['code']: e for e in entries}
        self.assertEqual(len(catalog), 35)
        self.assertEqual(catalog['W02']['quantity'], '8 条')
        self.assertEqual(catalog['W08']['quantity'], '2 块')
        self.assertEqual(catalog['W06']['stock_mm'], [426, 98, 8])
        self.assertEqual(catalog['E06']['drawings'], ['C-P01'])
        self.assertEqual(catalog['K07']['drawings'], ['C-P09'])
        self.assertEqual(catalog['E01']['drawings'], ['C-P04', 'C-P05'])
        self.assertNotIn('Platter', {n for e in entries for n in e['ids']})
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


if __name__ == '__main__':
    unittest.main()
