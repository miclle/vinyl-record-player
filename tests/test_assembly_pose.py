"""The saved viewing pose must round-trip without changing engineering geometry."""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
import FreeCAD as App

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from assembly_pose import set_cover_angle
from hinges import moving_names, rotation
import drawing_data


class AssemblyPoseTests(unittest.TestCase):
    def test_saved_open_cover_round_trips_and_drawings_use_closed_datum(self):
        source=ROOT/'cad/record-player.FCStd'
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'PoseTest.FCStd'
            shutil.copy2(source,path)
            doc=App.openDocument(str(path))
            try:
                p=json.loads(doc.GeometryDatums.BuildParametersJSON)
                self.assertEqual(float(doc.AssemblyState.CoverAngle),70)
                opened={name:doc.getObject(name).Shape.copy() for name in moving_names()}
                fixed={name:doc.getObject(name).Shape.copy() for name in ['Back','HingeBase0','HingeBase1']}
                for _ in range(3):
                    set_cover_angle(doc,p,0)
                    for name in moving_names():
                        expected=opened[name].copy()
                        expected.Placement=rotation(p,70).inverse().multiply(expected.Placement)
                        actual=doc.getObject(name).Shape
                        self.assertLess(actual.cut(expected).Volume+expected.cut(actual).Volume,1e-5,name)
                    self.assertAlmostEqual(doc.DustCover.Shape.optimalBoundingBox(False).ZMax,p['closed_height'])
                    set_cover_angle(doc,p,70)
                for name,expected in {**opened,**fixed}.items():
                    actual=doc.getObject(name).Shape
                    self.assertLess(actual.cut(expected).Volume+expected.cut(actual).Volume,1e-5,name)
                with self.assertRaises(ValueError):
                    set_cover_angle(doc,p,71)
            finally:
                App.closeDocument(doc.Name)
        data=drawing_data.collect(ROOT,project=False)
        cover=next(c for c in data['cards'] if c['key']=='DustCover')
        self.assertAlmostEqual(cover['origin_mm'][2]+cover['size_mm'][2],p['closed_height'])
        self.assertEqual(digest,hashlib.sha256(source.read_bytes()).hexdigest())
