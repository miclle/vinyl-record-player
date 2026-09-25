"""The guide must map the current assembly, not the historical mechanism."""
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
from wood_stock import RETIRED_WOOD_CODES, stock_rows


class AssemblyGuideTests(unittest.TestCase):
    def test_overview_targets_exist_with_one_three_seven_or_eight_slats(self):
        data = drawing_data.collect(ROOT, project=False)
        for count in (1, 3, 7, 8):
            with self.subTest(slat_count=count):
                changed = copy.deepcopy(data)
                for card in changed['cards']:
                    if 'Slat01' in card['ids']:
                        card['ids'] = card['ids'][:count]
                        card['quantity'] = count
                entries = assembly_guide.catalog_from_drawings(changed)
                targets = assembly_guide.overview_targets(entries)
                catalog = {e['code']: e for e in entries}
                self.assertEqual(catalog['W02']['quantity'], f'{count} 条')
                self.assertEqual(set(targets), {e['code'] for e in entries if e['page'] == 1})
                for code, (name, fraction) in targets.items():
                    self.assertIn(name, catalog[code]['ids'])
                if count in (7, 8):
                    self.assertEqual(targets['W02'][0], 'Slat04')

    def test_selected_objects_have_unique_codes_and_current_drawing_references(self):
        paths = list((ROOT/'cad').glob('*.FCStd'))
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        data = drawing_data.collect(ROOT, project=False)
        entries = assembly_guide.catalog_from_drawings(data)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'GuideTest.FCStd'
            shutil.copy2(ROOT/'cad/record-player.FCStd', path)
            doc = App.openDocument(str(path))
            try:
                self.assertEqual(assembly_guide.check_coverage(doc, entries), 64)
                with self.assertRaisesRegex(ValueError, 'coverage mismatch'):
                    assembly_guide.check_coverage(doc, entries[:-1])
                with self.assertRaisesRegex(ValueError, 'duplicate=True'):
                    assembly_guide.check_coverage(doc, entries+[copy.deepcopy(entries[0])])
            finally:
                App.closeDocument(doc.Name)
        catalog = {e['code']: e for e in entries}
        self.assertEqual(len(catalog), 35)
        self.assertEqual(catalog['W02']['quantity'], '7 条')
        self.assertEqual(catalog['W08']['quantity'], '2 块')
        params = data['parameters']
        self.assertEqual(catalog['W06']['stock_mm'],
                         [426, 98, params['acoustic']['baffle_thickness']])
        self.assertEqual(catalog['E06']['drawings'], ['C-P01'])
        self.assertEqual(catalog['K07']['drawings'], ['C-P09'])
        self.assertEqual(catalog['E01']['drawings'], ['C-P04', 'C-P05'])
        self.assertNotIn('Platter', {n for e in entries for n in e['ids']})
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})

    def test_wood_stock_catalog_matches_guide_exactly(self):
        data = drawing_data.collect(ROOT, project=False)
        expected = stock_rows(data['cards'])
        entries = [entry for entry in assembly_guide.catalog_from_drawings(data)
                   if entry['code'].startswith('W')]
        self.assertEqual([entry['code'] for entry in entries],
                         [row['code'] for row in expected])
        self.assertEqual(sum(entry['stock_count'] for entry in entries), 20)
        self.assertEqual(RETIRED_WOOD_CODES, {
            'W05': '原独立下横梁与底板完全重叠，已取消；编号保留不重排。',
        })
        for entry, row in zip(entries, expected):
            self.assertEqual(entry['title'], row['title'])
            self.assertEqual(entry['ids'], row['ids'])
            self.assertEqual(entry['stock_count'], row['quantity'])
            self.assertEqual(entry['stock_mm'], row['stock_mm'])
            self.assertEqual(entry['stock_note'], row['stock_note'])


if __name__ == '__main__':
    unittest.main()
