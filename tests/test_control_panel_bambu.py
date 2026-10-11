"""Read native project meshes in assembly coordinates and verify current split materials."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import update_control_panel_bambu as native


class NativeProjectTests(unittest.TestCase):
    def test_both_native_projects_match_current_stls_and_nozzle_profiles(self):
        for name,nozzle,layer in (('Control-panel-bambu.3mf','0.4','0.2'),
                                  ('Control-panel-bambu-0.2mm.3mf','0.2','0.1')):
            with self.subTest(project=name):
                result=native.verify(native.OUT/name)
                self.assertTrue(result['passed'])
                self.assertEqual(result['filament_colour'],['#000000','#FFFFFF'])
                self.assertEqual(result['nozzle_diameter'],[nozzle])
                self.assertEqual(result['layer_height'],layer)
                self.assertEqual(result['total_height_mm'],3.9)
                self.assertEqual(result['top_shell_thickness'],'0.8')
                self.assertEqual(result['top_surface_pattern'],'monotonicline')
                self.assertEqual(result['top_surface_speed'],['30','30'])
                self.assertEqual(result['ironing_type'],'no ironing')
                self.assertEqual(result['support_enabled'],'0')
                self.assertEqual(result['wipe_tower_xy_mm'][0],['180'])
                self.assertEqual([r['extruder'] for r in result['geometry_readback']],[1,2])


if __name__=='__main__':
    unittest.main()
