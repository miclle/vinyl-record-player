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


if __name__=='__main__':unittest.main()
