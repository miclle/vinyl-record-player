"""8-F5 vendor drawing: horizontal installation and conservative fit volumes."""
import FreeCAD as App
import Part

V = App.Vector


def rounded_prism(cx, cz, width, height, radius, y, depth):
    """Rounded rectangle in XZ, extruded along Y; dimensions are outside bounds."""
    if min(width, height, depth, radius) <= 0 or 2 * radius >= min(width, height):
        raise ValueError('Invalid rounded opening dimensions')
    x, z = cx - width / 2, cz - height / 2
    shape = Part.makeBox(width - 2 * radius, depth, height, V(x + radius, y, z))
    shape = shape.fuse(Part.makeBox(width, depth, height - 2 * radius, V(x, y, z + radius)))
    for px in (x + radius, x + width - radius):
        for pz in (z + radius, z + height - radius):
            shape = shape.fuse(Part.makeCylinder(radius, depth, V(px, y, pz), V(0, 1, 0)))
    return shape.removeSplitter()


def installation(p):
    s = p['ac_inlet']
    x, z, rear, wall = s['center_x'], s['center_z'], p['depth'], p['wall']
    opening = rounded_prism(x, z, s['cutout_width'], s['cutout_height'],
                            s['cutout_radius'], rear - wall, wall)
    bolts = [Part.makeCylinder(s['mount_hole_diameter'] / 2, wall + s['flange_thickness'],
                              V(x, rear - wall, z + sign * s['mount_hole_pitch'] / 2), V(0, 1, 0))
             for sign in (-1, 1)]
    flange = rounded_prism(x, z, s['flange_width'], s['flange_height'],
                           s['flange_corner_radius_assumption'], rear, s['flange_thickness'])
    front = rear + s['flange_thickness']
    terminal_y = front - s['total_depth']
    body = rounded_prism(x, z, s['body_width'], s['body_height'],
                         s['body_corner_radius_assumption'], terminal_y, rear - terminal_y)
    envelope = flange.fuse(body)
    for bolt in bolts:
        envelope = envelope.cut(bolt)
    wiring = Part.makeBox(s['cutout_width'], s['wire_clearance_assumption'], s['cutout_height'],
                          V(x - s['cutout_width'] / 2, terminal_y - s['wire_clearance_assumption'],
                            z - s['cutout_height'] / 2))
    return opening, bolts, envelope.removeSplitter(), wiring
