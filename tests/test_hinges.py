"""Saved mounting holes, material retention and moving hardware regressions."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import FreeCAD as App
import Part

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import hinges


class HingeTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path=Path(tmp.name)/'HingeReadback.FCStd'
        shutil.copy2(ROOT/'cad/lumi-three-driver.FCStd',path)
        self.doc=App.openDocument(str(path))
        self.addCleanup(App.closeDocument,self.doc.Name)
        self.p=json.loads((ROOT/'cad/parameters.json').read_text())

    def test_saved_installation_holes_and_one_degree_sweep(self):
        checks,metrics=hinges.check_installation(self.doc,self.p)
        self.assertTrue(all(checks.values()),(checks,metrics))
        self.assertEqual(metrics['sample_count'],71)
        self.assertEqual(metrics['axis_mm'],[0,356.95,147])
        # Independently read holes and the retained back-panel material.
        for x in (83,117,333,367):
            self.assertFalse(self.doc.Back.Shape.isInside(App.Vector(x,346,130),1e-6,False))
            self.assertTrue(self.doc.Back.Shape.isInside(App.Vector(x,340,130),1e-6,False))
            self.assertFalse(self.doc.DustCover.Shape.isInside(App.Vector(x,346.5,164),1e-6,False))
        self.assertAlmostEqual(metrics['bare_cover_closed_moment_estimate_nm'],1.51354,places=4)

    def test_filled_pilot_and_through_drilled_back_are_rejected(self):
        back=self.doc.Back; original=back.Shape.copy()
        back.Shape=original.fuse(Part.makeCylinder(1.5,8,App.Vector(83,342,130),App.Vector(0,1,0)))
        checks,_=hinges.check_installation(self.doc,self.p,70)
        self.assertFalse(checks['hinge_mount_holes_clear'])
        back.Shape=original.cut(Part.makeCylinder(1.5,12,App.Vector(83,338,130),App.Vector(0,1,0)))
        checks,_=hinges.check_installation(self.doc,self.p,70)
        self.assertFalse(checks['hinge_mount_material_and_blind_depth'])

    def test_upper_backing_collision_is_not_hidden_by_clear_cover(self):
        # Put a stationary obstacle only inside the upper backing plate.
        obstacle=self.doc.addObject('Part::Feature','BackingObstacle')
        obstacle.Shape=Part.makeBox(2,1,2,App.Vector(99,343.5,162))
        checks,metrics=hinges.check_installation(self.doc,self.p,70)
        self.assertFalse(checks['hinge_cover_assembly_sweep_clear'])
        self.assertIn('BackingObstacle',[c['part'] for c in metrics['collisions']])
        self.assertLess(self.doc.DustCover.Shape.common(obstacle.Shape).Volume,1e-6)

    def test_drawing_holes_follow_saved_mounting_positions(self):
        from drawing_details import panel_details
        data={s['key']:s for s in panel_details(self.doc,self.p,None,False)}
        cover=data['DustCover']
        self.assertEqual([(h['u_mm'],h['v_mm']) for h in cover['holes']],
                         [(71,16.5),(105,16.5),(321,16.5),(355,16.5)])
        pilots=[h for h in data['Back']['holes'] if h['id'].startswith('J')]
        self.assertEqual([(h['u_mm'],h['v_mm'],h['depth_mm']) for h in pilots],
                         [(71,95.5,8),(105,95.5,8),(321,95.5,8),(355,95.5,8)])


if __name__=='__main__':
    unittest.main()
