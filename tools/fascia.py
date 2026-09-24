"""Front-facing T extrusion and its roof rebate; fastening remains unconfirmed."""
import math

import FreeCAD as App
import Part

V = App.Vector


def dimensions(p):
    s = p['fascia']
    height, depth, thickness = s['face_height'], s['overall_depth'], s['thickness']
    gap, clearance = s['end_gap_assumption'], s['fit_clearance_assumption']
    roof = p['acoustic']
    top = p['cabinet_top']
    web_bottom = top-height/2-thickness/2
    floor = web_bottom-clearance
    front = thickness+clearance
    rear = depth+clearance
    roof_top = roof['roof_bottom_z']+roof['roof_thickness']
    baffle_front = 16+(roof['roof_bottom_z']-p['foot_height']-p['wall'])/math.tan(math.radians(p['front_angle']))
    if not (0 < thickness < min(height, depth) and gap >= 0 and clearance >= 0
            and 2*gap < p['width']-2*p['wall']
            and roof['roof_bottom_z'] < floor < roof_top and rear < baffle_front):
        raise ValueError('T fascia rebate must retain roof thickness and stay ahead of the chamber seal')
    return dict(length=p['width']-2*p['wall']-2*gap, x=p['wall']+gap,
                bottom=top-height, web_bottom=web_bottom, rebate_floor=floor,
                face_rear=thickness, roof_front=front, rebate_rear=rear,
                rebate_depth=roof_top-floor,
                remaining_roof=floor-roof['roof_bottom_z'], seal_margin=baffle_front-rear)


def installation(p):
    s = p['fascia']; d = dimensions(p)
    t, roof = s['thickness'], p['acoustic']
    face = Part.makeBox(d['length'], t, s['face_height'], V(d['x'], 0, d['bottom']))
    web = Part.makeBox(d['length'], s['overall_depth']-t, t, V(d['x'], t, d['web_bottom']))
    # Machine across the full roof width; both cuts lie ahead of the sealed baffle joint.
    width = p['width']-2*p['wall']
    front_cut = Part.makeBox(width, d['roof_front'], roof['roof_thickness']+2,
                             V(p['wall'], 0, roof['roof_bottom_z']-1))
    rebate = Part.makeBox(width, d['rebate_rear']-d['roof_front'], d['rebate_depth']+1,
                         V(p['wall'], d['roof_front'], d['rebate_floor']))
    return face.fuse(web).removeSplitter(), [front_cut, rebate]
