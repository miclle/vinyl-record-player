"""Reject guides whose leaders would identify hidden or missing components."""
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))


@unittest.skipUnless(importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdf'),
                     'Run in the separate PDF runtime')
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

    def test_guide_is_inserted_after_stock_page_without_duplication(self):
        from pypdf import PdfReader
        from reportlab.pdfgen import canvas
        from assembly_guide_pdf import (BOOK_01_BASE_CODES, EMBEDDED_GUIDE_MARKER,
                                        embed_guide_in_book)

        def write_pdf(path, pagesize, labels, source_sha256=None):
            pdf = canvas.Canvas(str(path), pagesize=pagesize)
            for label in labels:
                pdf.bookmarkPage(label)
                pdf.addOutlineEntry(label, label)
                pdf.drawString(36, pagesize[1] - 36, label)
                if source_sha256 and label == 'A-00':
                    pdf.drawString(36, pagesize[1] - 54, source_sha256)
                pdf.showPage()
            pdf.save()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            book, guide = root/'book.pdf', root/'guide.pdf'
            source_sha256 = 'a'*64
            write_pdf(book, (420/25.4*72, 297/25.4*72), BOOK_01_BASE_CODES,
                      source_sha256)
            write_pdf(guide, (594/25.4*72, 420/25.4*72), ('G-01', 'G-02'))
            options = dict(expected_source_sha256=source_sha256,
                           expected_base_codes=BOOK_01_BASE_CODES)
            self.assertEqual(embed_guide_in_book(guide, book, **options), 19)
            self.assertEqual(embed_guide_in_book(guide, book, **options), 19)

            combined = PdfReader(book)
            labels = [(page.extract_text() or '').splitlines()[0]
                      for page in combined.pages]
            self.assertEqual(labels[:5], ['A-00', 'A-STOCK', 'G-01', 'G-02', 'A-01'])
            outline_titles = [item.title for item in combined.outline
                              if not isinstance(item, list)]
            self.assertEqual(outline_titles[:5],
                             ['A-00', 'A-STOCK', 'G-01  整机外观导览',
                              'G-02  内部结构导览', 'A-01'])
            self.assertTrue(all(bool(page.get(EMBEDDED_GUIDE_MARKER, False))
                                for page in combined.pages[2:4]))
            self.assertAlmostEqual(float(combined.pages[2].mediabox.width)*25.4/72,
                                   594, places=2)
            self.assertAlmostEqual(float(combined.pages[2].mediabox.height)*25.4/72,
                                   420, places=2)
            with self.assertRaisesRegex(ValueError, 'source CAD hash differs'):
                embed_guide_in_book(guide, book, expected_source_sha256='b'*64,
                                    expected_base_codes=BOOK_01_BASE_CODES)

            incomplete = root/'incomplete.pdf'
            write_pdf(incomplete, (420/25.4*72, 297/25.4*72),
                      BOOK_01_BASE_CODES[:-1], source_sha256)
            with self.assertRaisesRegex(ValueError, '16 base pages'):
                embed_guide_in_book(guide, incomplete, **options)

    def test_failed_preview_render_does_not_publish_partial_outputs(self):
        import assembly_guide_pdf

        data = {
            'entries': [{'code': 'W01', 'page': 1, 'stock_count': 1}],
            'views': {
                'overview': {'anchors': {'W01': [0, 0]}, 'occluded_by': {}},
                'exploded': {'anchors': {}, 'occluded_by': {}},
                'rear': {'anchors': {code: [0, 0]
                                     for code in ('W04', 'E05', 'E06', 'A03')},
                         'occluded_by': {}},
            },
        }

        class FakeGuide:
            def __init__(self, root, guide_data, output, font):
                self.output = output

            def make(self):
                self.output.write_bytes(b'guide')

        def fake_embed(guide, book, output_path=None, **options):
            Path(output_path).write_bytes(b'combined')
            return 19

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'tmp/assembly-guide').mkdir(parents=True)
            (root/'output/pdf').mkdir(parents=True)
            (root/'cad').mkdir()
            (root/'previews').mkdir()
            source = root/'cad/record-player.FCStd'
            source.write_bytes(b'cad')
            data['sources'] = {
                source.name: hashlib.sha256(source.read_bytes()).hexdigest(),
            }
            (root/'tmp/assembly-guide/manifest.json').write_text(json.dumps(data))
            sentinels = {
                root/'output/pdf/01-assembly-and-enclosure.pdf': b'base',
                root/'cad/assembly-guide-index.json': b'index',
                root/'previews/assembly-guide-1.png': b'preview-1',
                root/'previews/assembly-guide-2.png': b'preview-2',
            }
            for path, content in sentinels.items():
                path.write_bytes(content)
            with patch.object(assembly_guide_pdf, 'Guide', FakeGuide), \
                 patch.object(assembly_guide_pdf, 'embed_guide_in_book', fake_embed), \
                 patch.object(assembly_guide_pdf.shutil, 'which', return_value='pdftoppm'), \
                 patch.object(assembly_guide_pdf.subprocess, 'run',
                              side_effect=subprocess.CalledProcessError(1, 'pdftoppm')):
                with self.assertRaises(subprocess.CalledProcessError):
                    assembly_guide_pdf.make(root=root, font=Path('unused'))
            for path, content in sentinels.items():
                self.assertEqual(path.read_bytes(), content)
            self.assertFalse((root/'tmp/assembly-guide/guide-pages.pdf').exists())


if __name__ == '__main__':
    unittest.main()
