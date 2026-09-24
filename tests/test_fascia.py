"""Saved T section, roof shelf and closure must survive the new installation."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import FreeCAD as App
import Part

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_model
import validate_model
import fascia


class FasciaTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        (self.root/'cad').mkdir()
        (self.root/'cad/parameters.json').write_bytes((ROOT/'cad/parameters.json').read_bytes())
        (self.root / 'cad/selected-mechanism.json').write_bytes((ROOT / 'cad/selected-mechanism.json').read_bytes())
        with patch.object(build_model,'ROOT',self.root):
            doc,self.p,_=build_model.deliver()
        App.closeDocument(doc.Name)
        self.doc=App.openDocument(str(self.root/'cad/lumi-selected-mechanism-fit.FCStd'))
        from assembly_pose import set_cover_angle
        set_cover_angle(self.doc,self.p,0)
        self.addCleanup(App.closeDocument,self.doc.Name)

    def test_saved_section_shelf_clearances_and_chambers(self):
        shape=self.doc.Fascia.Shape
        b=shape.optimalBoundingBox(False)
        self.assertEqual([b.XLength,b.YLength,b.ZLength],[425,30,30])
        self.assertAlmostEqual(shape.Volume,425*(30*5+25*5))
        self.assertTrue(shape.isInside(App.Vector(225,20,131),1e-6,False))
        self.assertFalse(shape.isInside(App.Vector(225,20,143),1e-6,False))
        checks,m=validate_model.check_fascia(self.doc,self.p)
        self.assertTrue(all(checks.values()),(checks,m))
        self.assertAlmostEqual(m['closed_cover_gap_mm'],1)
        self.assertAlmostEqual(m['remaining_roof_mm'],4.3)
        self.assertAlmostEqual(m['rebate_depth_mm'],3.7)
        # Coordinates independent of the geometry helper verify actual shelf and slot.
        roof=self.doc.AcousticRoof.Shape
        self.assertTrue(roof.isInside(App.Vector(225,20,128),1e-6,False))
        self.assertFalse(roof.isInside(App.Vector(225,20,130),1e-6,False))
        self.assertFalse(roof.isInside(App.Vector(225,3,127),1e-6,False))
        checks,_=validate_model.check_acoustics(self.doc,self.p,[])
        self.assertTrue(checks['three_independent_enclosed_chambers'])

    def test_rectangle_in_same_bounds_cannot_masquerade_as_t_section(self):
        self.doc.Fascia.Shape=Part.makeBox(425,30,30,App.Vector(12.5,0,116.5))
        checks,_=validate_model.check_fascia(self.doc,self.p)
        self.assertFalse(checks['fascia_t_section_matches'])

    def test_filled_rebate_and_removed_shelf_are_detected(self):
        roof=self.doc.AcousticRoof; original=roof.Shape.copy()
        roof.Shape=original.fuse(Part.makeBox(426,25,3.7,App.Vector(12,5.2,128.8)))
        checks,_=validate_model.check_fascia(self.doc,self.p)
        self.assertFalse(checks['fascia_roof_rebate_and_shelf_match'])
        self.assertFalse(checks['fascia_neighbors_clear'])
        roof.Shape=original.cut(Part.makeBox(426,25,8,App.Vector(12,5.2,124.5)))
        checks,_=validate_model.check_fascia(self.doc,self.p)
        self.assertFalse(checks['fascia_roof_rebate_and_shelf_match'])

    def test_roof_top_placement_hits_cover(self):
        self.doc.Fascia.Placement.Base.z=3.5
        checks,m=validate_model.check_fascia(self.doc,self.p)
        self.assertFalse(checks['fascia_neighbors_clear'])
        self.assertIn('DustCover',[hit['part'] for hit in m['collisions']])

    def test_unsafe_rebate_rejected_before_build(self):
        self.p['fascia']['overall_depth']=50
        with self.assertRaisesRegex(ValueError,'chamber seal'):
            fascia.dimensions(self.p)


if __name__=='__main__':
    unittest.main()
