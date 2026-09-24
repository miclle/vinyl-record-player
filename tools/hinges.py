"""HFA5751-3434 installation; nominal vendor dimensions plus explicit assumptions.

Knuckles and necks are simplified envelopes, not a reverse-engineered friction
mechanism. Fixed and moving leaves are separate so every preview uses one axis.
"""
import FreeCAD as App
import Part

V = App.Vector


def dimensions(p):
    h = p['hinges']
    # Rear cover is inset 2 mm relative to the cabinet in the current layout.
    rear = p['depth'] - 2
    axis_z = (p['cabinet_top'] + p['cover_bottom']) / 2
    radius = h['barrel_diameter_assumption'] / 2
    axis_y = p['depth'] + h['overall_projection_assumption'] - radius
    if not 0 < h['wood_pilot_depth_assumption'] < p['wall']:
        raise ValueError('Hinge wood pilots must remain blind')
    if len(h['center_x']) != 2 or h['plate_height_assumption'] >= h['hole_pitch']:
        raise ValueError('Expected two hinges with separate upper reinforcement plates')
    return dict(axis=V(0, axis_y, axis_z), rear=rear, spacer=p['depth']-rear,
                top_hole_z=axis_z+h['hole_pitch']/2,
                bottom_hole_z=axis_z-h['hole_pitch']/2)


def moving_names():
    return ['DustCover'] + [f'{prefix}{i}' for i in range(2)
                           for prefix in ('HingePin', 'HingeSpacer', 'HingeBacking')]


def rotation(p, angle):
    return App.Placement(V(), App.Rotation(V(1, 0, 0), -angle), dimensions(p)['axis'])


def installation(p):
    h = p['hinges']; d = dimensions(p)
    width, height, t = h['axis_length'], h['unfolded_height'], h['leaf_thickness']
    y, z = p['depth'], d['axis'].z
    radius = h['barrel_diameter_assumption']/2
    half_pitch = h['hole_pitch']/2
    gap = h['knuckle_gap_assumption']
    items = []
    for x in h['center_x']:
        left, right = x-width/2, x+width/2
        fixed = Part.makeBox(width, t, height/2-7, V(left, y, z-height/2))
        for start, end in ((left, x-half_pitch-gap/2), (x+half_pitch+gap/2, right)):
            fixed = fixed.fuse(Part.makeBox(end-start, t, 8, V(start, y, z-8)))
            fixed = fixed.fuse(Part.makeCylinder(radius, end-start,
                               V(start, d['axis'].y, z), V(1, 0, 0)))
        moving = Part.makeBox(width, t, height/2-7, V(left, y, z+7))
        moving = moving.fuse(Part.makeBox(h['hole_pitch']-gap, t, 8,
                            V(x-half_pitch+gap/2, y, z)))
        moving = moving.fuse(Part.makeCylinder(radius, h['hole_pitch']-gap,
                             V(x-half_pitch+gap/2, d['axis'].y, z), V(1, 0, 0)))
        ph = h['plate_height_assumption']; pt = h['backing_thickness_assumption']
        spacer = Part.makeBox(width, d['spacer'], ph,
                              V(left, d['rear'], d['top_hole_z']-ph/2))
        backing = Part.makeBox(width, pt, ph,
                               V(left, d['rear']-p['cover_wall']-pt, d['top_hole_z']-ph/2))
        cover_cuts, wood_cuts = [], []
        for hx in (x-half_pitch, x+half_pitch):
            for hz, target in ((d['bottom_hole_z'], 'fixed'), (d['top_hole_z'], 'moving')):
                cut = Part.makeCylinder(h['hole_diameter']/2, t+2, V(hx, y-1, hz), V(0, 1, 0))
                if target == 'fixed':
                    fixed = fixed.cut(cut)
                else:
                    moving = moving.cut(cut)
            cut = Part.makeCylinder(h['cover_hole_diameter_assumption']/2,
                                    p['cover_wall']+pt+d['spacer']+2,
                                    V(hx, d['rear']-p['cover_wall']-pt-1, d['top_hole_z']), V(0, 1, 0))
            spacer = spacer.cut(cut); backing = backing.cut(cut); cover_cuts.append(cut)
            wood_cuts.append(Part.makeCylinder(h['wood_pilot_diameter_assumption']/2,
                             h['wood_pilot_depth_assumption']+1,
                             V(hx, y-h['wood_pilot_depth_assumption'], d['bottom_hole_z']), V(0, 1, 0)))
        items.append(dict(fixed=fixed.removeSplitter(), moving=moving.removeSplitter(),
                          spacer=spacer, backing=backing, cover_cuts=cover_cuts, wood_cuts=wood_cuts))
    return items


def interference_volume(first, second):
    """A solid bounding-box probe rejects hollow-cover false positives cheaply.

    Unlike surface distance, this also preserves full-solid containment. The
    second shape is wholly inside its box; zero box intersection proves zero
    part intersection without running a boolean against a curved arm surface.
    """
    bounds = second.BoundBox
    if not first.BoundBox.intersect(bounds):
        return 0.0
    box = Part.makeBox(bounds.XLength, bounds.YLength, bounds.ZLength,
                       V(bounds.XMin, bounds.YMin, bounds.ZMin))
    if first.common(box).Volume < 1e-9:
        return 0.0
    return first.common(second).Volume


def check_installation(doc, p, step=1):
    """Check saved solids, fastener paths and sampled motion against all neighbors."""
    h = p['hinges']; d = dimensions(p)
    checks = {}; metrics = {}; holes_ok = True; support_ok = True
    for i, x in enumerate(h['center_x']):
        for hx in (x-h['hole_pitch']/2, x+h['hole_pitch']/2):
            for name, hz, y0, length, diameter in (
                    (f'HingeBase{i}', d['bottom_hole_z'], p['depth'], h['leaf_thickness'], h['hole_diameter']),
                    (f'HingePin{i}', d['top_hole_z'], p['depth'], h['leaf_thickness'], h['hole_diameter']),
                    ('DustCover', d['top_hole_z'], d['rear']-p['cover_wall'], p['cover_wall'], h['cover_hole_diameter_assumption']),
                    ('Back', d['bottom_hole_z'], p['depth']-h['wood_pilot_depth_assumption'], h['wood_pilot_depth_assumption'], h['wood_pilot_diameter_assumption'])):
                shape = doc.getObject(name).Shape
                probe = Part.makeCylinder(diameter/2-0.01, length-0.02, V(hx, y0+0.01, hz), V(0,1,0))
                holes_ok &= shape.common(probe).Volume < 1e-6
                # Material just outside the hole proves this is a supported hole, not empty space.
                support_ok &= shape.isInside(V(hx+diameter/2+0.3,y0+length/2,hz),1e-6,False)
            support_ok &= doc.Back.Shape.isInside(V(hx,p['depth']-h['wood_pilot_depth_assumption']-0.2,d['bottom_hole_z']),1e-6,False)
    checks['hinge_mount_holes_clear'] = bool(holes_ok)
    checks['hinge_mount_material_and_blind_depth'] = bool(support_ok)
    expected = installation(p)
    checks['hinge_saved_shapes_match'] = all(
        doc.getObject(f'{prefix}{i}').Shape.cut(item[key]).Volume < 1e-5 and
        item[key].cut(doc.getObject(f'{prefix}{i}').Shape).Volume < 1e-5
        for i,item in enumerate(expected)
        for prefix,key in [('HingeBase','fixed'),('HingePin','moving'),('HingeSpacer','spacer'),('HingeBacking','backing')])
    names = moving_names()
    moving = Part.makeCompound([doc.getObject(n).Shape for n in names])
    stationary = [o for o in doc.Objects if o.TypeId=='Part::Feature' and o.Name not in names
                  and not getattr(o,'IsDiagnostic',False)]
    collisions = []
    angles = sorted(set([float(a) for a in range(0,int(p['cover_angle_open'])+1,step)]+[p['cover_angle_open']]))
    for angle in angles:
        shape = moving.copy(); shape.rotate(d['axis'],V(1,0,0),-angle)
        for obj in stationary:
            overlap = interference_volume(shape, obj.Shape)
            if overlap > 1e-5:
                collisions.append(dict(angle_degrees=angle,part=obj.Name,volume_mm3=round(overlap,6)))
    # Check all stationary hinge hardware against neighbors as well.
    fixed_hits = []
    for i in range(2):
        obj=doc.getObject(f'HingeBase{i}')
        for other in stationary:
            if obj!=other and obj.Shape.BoundBox.intersect(other.Shape.BoundBox):
                overlap=obj.Shape.common(other.Shape).Volume
                if overlap>1e-5:fixed_hits.append(dict(part=obj.Name,neighbor=other.Name,volume_mm3=overlap))
    checks['hinge_fixed_neighbors_clear'] = not fixed_hits
    checks['hinge_cover_assembly_sweep_clear'] = not collisions
    checks['hinge_installation_unreleased'] = all(not doc.getObject(f'{prefix}{i}').InstallationReleased
                  for i in range(2) for prefix in ('HingeBase','HingePin','HingeSpacer','HingeBacking'))
    # Bare drilled cover only: metal/fasteners are excluded rather than assigned invented mass.
    lid=doc.DustCover.Shape
    com=sum((s.CenterOfMass*s.Volume for s in lid.Solids),V())/lid.Volume
    mass=lid.Volume*h['acrylic_density_assumption_g_cm3']*1e-6
    moment=mass*9.80665*(d['axis'].y-com.y)/1000
    metrics.update(axis_mm=list(d['axis']),sample_step_degrees=step,sample_count=len(angles),
                   collisions=collisions,fixed_collisions=fixed_hits,
                   bare_cover_mass_estimate_kg=mass,bare_cover_closed_moment_estimate_nm=moment,
                   max_torque_user_reported_nm=h['max_torque_user_reported_nm'],
                   torque_scope=h['torque_scope'],installation_released=False)
    return checks,metrics
