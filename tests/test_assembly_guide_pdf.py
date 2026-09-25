"""Reject guides whose leaders would identify hidden or missing components."""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))


@unittest.skipUnless(importlib.util.find_spec('reportlab'), 'Run in the separate PDF runtime')
class GuideAnnotationTests(unittest.TestCase):
    def test_missing_or_occluded_callouts_prevent_publication(self):
        from assembly_guide_pdf import validate_annotations
        data = {'entries': [{'code': 'W01', 'page': 1, 'stock_count': 2},
                            {'code': 'W03', 'page': 2, 'stock_count': 1},
                            {'code': 'W04', 'page': 2, 'stock_count': 1},
                            {'code': 'E05', 'page': 2}, {'code': 'E06', 'page': 2},
                            {'code': 'A03', 'page': 2}],
                'views': {key: {'anchors': dict.fromkeys(codes, [0.5, 0.5]), 'occluded_by': {}}
                          for key, codes in [('overview', ['W01']),
                                             ('exploded', ['W03', 'A03']),
                                             ('rear', ['W04', 'E05', 'E06', 'A03'])]}}
        validate_annotations(data)
        for key, missing in [('overview', True), ('exploded', False)]:
            broken = copy.deepcopy(data)
            if missing:
                broken['views'][key]['anchors'].pop('W01')
            else:
                broken['views'][key]['occluded_by']['W03'] = ['AcousticDividerLeft']
            with self.assertRaisesRegex(ValueError, 'Unusable annotations'):
                validate_annotations(broken)

    def test_stale_catalog_without_stock_counts_is_rejected(self):
        from assembly_guide_pdf import validate_annotations
        with self.assertRaisesRegex(ValueError, 'catalog is stale'):
            validate_annotations({'entries': [{'code': 'W01', 'page': 1}]})


if __name__ == '__main__':
    unittest.main()
