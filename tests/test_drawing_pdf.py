"""PDF geometry scale checks; run with reportlab and svglib installed."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
AVAILABLE=importlib.util.find_spec('reportlab') and importlib.util.find_spec('svglib')


@unittest.skipUnless(AVAILABLE, 'PDF runtime dependencies are separate from FreeCAD')
class PDFProjectionTests(unittest.TestCase):
    def test_svg_pixel_units_do_not_shrink_geometry_relative_to_dimensions(self):
        import drawing_pack
        self.assertTrue(hasattr(drawing_pack,'load_projection'))
        view={'size_mm':[80,40], 'svg':'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40" viewBox="0 0 80 40"><path d="M0 0 H80 V40 H0 Z" fill="none" stroke="black"/></svg>'}
        drawing=drawing_pack.load_projection(view)
        self.assertEqual(tuple(round(v,5) for v in drawing.getBounds()),(0,0,80,40))

    def test_drilling_sheet_records_blind_depth_and_coordinate_datum(self):
        import tempfile
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from pypdf import PdfReader
        import drawing_pack
        self.assertTrue(hasattr(drawing_pack, 'hole_sheet_page'))
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        sheet = dict(key='Bottom', code='A-H01', title='底板开孔', view='bottom',
                     axes=['X', 'Y'], size_mm=[100, 80], thickness_mm=12,
                     projection={'size_mm':[100,80], 'svg':'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="80"><path d="M0 0 H100 V80 H0 Z" fill="none" stroke="black"/></svg>'},
                     holes=[dict(id='P1.1',u_mm=35,v_mm=40,diameter_mm=3,kind='blind',depth_mm=8)],
                     notes=['底面盲孔；孔深 8，剩余木厚 4。'])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'holes.pdf'
            book=drawing_pack.Book(path,'开孔',{'revision':'test'},'STSong-Light')
            drawing_pack.hole_sheet_page(book,sheet)
            book.save()
            text=PdfReader(path).pages[0].extract_text()
            for expected in ('P1.1', '35', '40', 'Ø3', '深8', 'O', '+X', '+Y'):
                self.assertIn(expected,text)

    def test_section_does_not_invent_horizontal_edges_across_sloping_void(self):
        import tempfile
        import pdfplumber
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        import drawing_pack
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        parts=[]
        for key,u,v,w,h in [('Baffle',16,34.5,37.654,90),('GrilleCloth',12,34.5,29.743,90),
                             ('Bottom',0,22.5,90,12),('AcousticRoof',0,124.5,90,8),
                             ('Slat04',18,67.5,5,7),('Fascia',0,126.5,6,20),
                             ('LowerRail',0,22.5,8,12)]:
            path=(f'M0 {h} L29.243 0 L{w} 0 L{w-29.243} {h} Z'
                  if key in ('Baffle','GrilleCloth') else f'M0 0 H{w} V{h} H0 Z')
            parts.append(dict(key=key,origin_mm=[u,v],size_mm=[w,h],projection=dict(size_mm=[w,h],
                              svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><path d="{path}" fill="none" stroke="black"/></svg>')))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'section.pdf'
            book=drawing_pack.Book(path,'剖视',{'revision':'test'},'STSong-Light')
            drawing_pack.section_page(book,dict(x_mm=225,y_limit_mm=90,parts=parts),
                                      dict(front_angle=72,slat_count=8,acoustic={'baffle_thickness':8}))
            book.save()
            with pdfplumber.open(path) as pdf:
                false_edges=[line for line in pdf.pages[0].lines
                             if abs(line['x0']/drawing_pack.MM-114)<0.01
                             and abs(line['x1']/drawing_pack.MM-151.654)<0.01
                             and abs(line['top']/drawing_pack.MM-103.5)<0.01]
            self.assertEqual(false_edges,[], 'Bounding rectangle edge is not a physical baffle edge')


if __name__=='__main__':unittest.main()
