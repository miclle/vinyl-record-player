"""Nominal purchased feet; pilot holes and pitch circle are installation assumptions."""
import math

import FreeCAD as App
import Part

V = App.Vector


def positions(p):
    s = p['feet']
    return [(x, y) for y in (s['front_y'], p['depth']-s['rear_inset'])
            for x in (s['side_inset'], p['width']-s['side_inset'])]


def installation(p):
    s = p['feet']
    h, t = s['rubber_height'], s['flange_thickness']
    z0, wall = p['foot_height'], p['wall']
    if abs(z0-h-t) > 1e-6:
        raise ValueError('Foot height must equal rubber height plus mount flange thickness')
    if not (0 < s['pilot_depth_assumption'] < wall
            and 0 < s['pilot_diameter_assumption'] < s['mount_hole_diameter']
            and 0 < s['stud_diameter'] < s['barrel_diameter'] < s['panel_hole_diameter_assumption']
            and s['stud_length'] > t+s['barrel_height']):
        raise ValueError('Invalid foot, through-hole or blind pilot dimensions')
    parts = []
    for x, y in positions(p):
        foot = Part.makeCylinder(s['rubber_diameter']/2, h, V(x, y, 0)).fuse(
            Part.makeCylinder(s['stud_diameter']/2, s['stud_length'], V(x, y, h)))
        mount = Part.makeCylinder(s['flange_diameter']/2, t, V(x, y, h)).fuse(
            Part.makeCylinder(s['barrel_diameter']/2, s['barrel_height'], V(x, y, z0)))
        # Thread represented by nominal major diameter, not helical teeth.
        mount = mount.cut(Part.makeCylinder(s['stud_diameter']/2,
                                           t+s['barrel_height']+2, V(x, y, h-1)))
        cutouts = [Part.makeCylinder(s['panel_hole_diameter_assumption']/2,
                                     wall+2, V(x, y, z0-1))]
        holes = []
        for angle in (0, 120, 240):
            r = s['mount_pitch_circle_assumption']/2
            hx, hy = x+r*math.cos(math.radians(angle)), y+r*math.sin(math.radians(angle))
            holes.append((hx, hy))
            mount = mount.cut(Part.makeCylinder(s['mount_hole_diameter']/2, t+2, V(hx, hy, h-1)))
            cutouts.append(Part.makeCylinder(s['pilot_diameter_assumption']/2,
                                             s['pilot_depth_assumption']+1, V(hx, hy, z0-1)))
        parts.append(dict(center=(x, y), foot=foot.removeSplitter(), mount=mount.removeSplitter(),
                          cutouts=cutouts, holes=holes))
    return parts
