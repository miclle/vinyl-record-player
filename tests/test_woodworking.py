"""Verify actual normal thickness, stock dimensions and sealed panel joints."""
import contextlib
import io
import json
import math
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


class WoodworkingTests(unittest.TestCase):
    def test_integer_stock_and_real_slope_thickness_keep_chambers_closed(self):
        for angle,baffle_thickness,slat_thickness in [(72,8,3),(70,10,4)]:
            with self.subTest(angle=angle), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'cad').mkdir()
                p=json.loads((ROOT/'cad/parameters.json').read_text())
                p.update(width=450,depth=350,front_angle=angle,slat_thickness=slat_thickness,
                         slat_face_width=7,slat_pitch=11)
                p['acoustic']['baffle_thickness']=baffle_thickness
                p['woofer']['center_x']=225
                p['fullrange']['center_x']=[80,370]
                p['acoustic_divider_x']=[129,313]
                (root/'cad/parameters.json').write_text(json.dumps(p))
                (root / 'cad/mechanism.json').write_bytes((ROOT / 'cad/mechanism.json').read_bytes())
                with patch.object(build_model,'ROOT',root):
                    doc,_,_,_=build_model.build()
                try:
                    normal=App.Vector(0,math.sin(math.radians(angle)),-math.cos(math.radians(angle)))
                    aligned=doc.Baffle.Shape.copy()
                    aligned.rotate(App.Vector(),App.Rotation(normal,App.Vector(0,0,1)).Axis,
                                   math.degrees(App.Rotation(normal,App.Vector(0,0,1)).Angle))
                    self.assertAlmostEqual(aligned.optimalBoundingBox(False).ZLength,baffle_thickness,places=6)
                    slat=doc.Slat01.Shape.copy()
                    slat.Placement=App.Placement(App.Vector(),App.Rotation(normal,App.Vector(0,0,1))).multiply(slat.Placement)
                    bb=slat.optimalBoundingBox(False)
                    for actual,want in zip([bb.XLength,bb.YLength,bb.ZLength],[426,7,slat_thickness]):
                        self.assertAlmostEqual(actual,want,places=6)
                    self.assertAlmostEqual(doc.Slat08.Shape.CenterOfMass.z-doc.Slat01.Shape.CenterOfMass.z,77,places=6)
                    self.assertIsNone(doc.getObject('LowerRail'))
                    front_edge=Part.makeBox(426,8,p['wall'],App.Vector(p['wall'],0,p['foot_height']))
                    self.assertLess(front_edge.cut(doc.Bottom.Shape).Volume,1e-6)
                    self.assertLess(doc.Baffle.Shape.distToShape(doc.Bottom.Shape)[0],1e-6)
                    self.assertEqual([doc.Bottom.StockLength.Value,doc.Bottom.StockWidth.Value,doc.Bottom.StockThickness.Value],[426,350,12])
                    self.assertEqual([doc.Slat01.StockLength.Value,doc.Slat01.StockWidth.Value,doc.Slat01.StockThickness.Value],[426,7,slat_thickness])
                    for name in ['AcousticRoof','AcousticRear','AcousticDividerLeft',
                                 'AcousticDividerRight','RearSupport','FloatingDeck']:
                        self.assertEqual(doc.getObject(name).StockThickness.Value,10,name)
                    support_checks,support_metrics=validate_model.check_deck_supports(doc,p)
                    self.assertTrue(all(support_checks.values()),(support_checks,support_metrics))
                    for obj in doc.Objects:
                        if hasattr(obj,'StockLength'):
                            self.assertEqual(obj.StockLength.Value,round(obj.StockLength.Value))
                            self.assertEqual(obj.StockWidth.Value,round(obj.StockWidth.Value))
                    result,_=validate_model.check_acoustics(doc,p,[])
                    self.assertTrue(result['three_independent_enclosed_chambers'])
                    for obj in [doc.AcousticDividerLeft,doc.AcousticDividerRight]:
                        self.assertLess(obj.Shape.common(doc.Baffle.Shape).Volume,1e-5)
                        self.assertLess(obj.Shape.distToShape(doc.Baffle.Shape)[0],1e-6)
                finally:App.closeDocument(doc.Name)

    def test_validator_detects_tampered_baffle_normal_thickness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'cad').mkdir()
            p=json.loads((ROOT/'cad/parameters.json').read_text())
            (root/'cad/parameters.json').write_text(json.dumps(p))
            (root / 'cad/mechanism.json').write_bytes((ROOT / 'cad/mechanism.json').read_bytes())
            with patch.object(build_model,'ROOT',root):doc,p,_=build_model.deliver()
            try:
                self.assertTrue(hasattr(validate_model,'check_woodworking'))
                good,_=validate_model.check_woodworking(doc,p)
                self.assertTrue(all(good.values()))
                # Keep the metadata but enlarge the actual back face geometry.
                extra=doc.Baffle.Shape.copy();extra.translate(App.Vector(0,0.5,0))
                doc.Baffle.Shape=doc.Baffle.Shape.fuse(extra)
                bad,_=validate_model.check_woodworking(doc,p)
                self.assertFalse(bad['wood_panel_normal_thickness_matches'])
            finally:App.closeDocument(doc.Name)

    def test_validator_detects_oversized_support_recesses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'cad').mkdir()
            p=json.loads((ROOT/'cad/parameters.json').read_text())
            (root/'cad/parameters.json').write_text(json.dumps(p))
            (root/'cad/mechanism.json').write_bytes((ROOT/'cad/mechanism.json').read_bytes())
            with patch.object(build_model,'ROOT',root):doc,p,_,_=build_model.build()
            try:
                support=p['deck_support'];radius=support['diameter']/2+2
                centers=[(44,100),(p['width']-44,100),(p['width']/2,295)]
                roof_top=p['acoustic']['roof_bottom_z']+p['acoustic']['roof_thickness']
                original=doc.AcousticRoof.Shape.copy()
                for x,y in centers:
                    doc.AcousticRoof.Shape=doc.AcousticRoof.Shape.cut(Part.makeCylinder(
                        radius,support['roof_recess_depth']+1,
                        App.Vector(x,y,roof_top-support['roof_recess_depth'])))
                checks,_=validate_model.check_deck_supports(doc,p)
                self.assertFalse(checks['deck_support_recesses_clear_and_seated'])
                doc.AcousticRoof.Shape=original

                deck_bottom=p['cabinet_top']-p['deck_thickness']
                for x,y in centers:
                    doc.FloatingDeck.Shape=doc.FloatingDeck.Shape.cut(Part.makeCylinder(
                        radius,support['deck_recess_depth']+1,
                        App.Vector(x,y,deck_bottom-1)))
                checks,_=validate_model.check_deck_supports(doc,p)
                self.assertFalse(checks['deck_support_recesses_clear_and_seated'])
            finally:App.closeDocument(doc.Name)


if __name__=='__main__':unittest.main()
