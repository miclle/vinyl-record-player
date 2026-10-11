"""Independent flat mounting plate and extended-stem knob; GUI-only export."""
import hashlib
import json
import math
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import FreeCAD as App
import Mesh
import MeshPart
import Part

ROOT = Path(__file__).resolve().parents[1]
PARAMETERS = ROOT / 'cad/led-pot-mount.json'
OUTPUT = ROOT / 'output/3d-print/led-pot-mount'
PARTS = {'Plate': 'LED-pot-plate', 'Knob': 'LED-pot-knob'}
REPORT = 'LED-pot-controls.json'
V = App.Vector


def load_parameters():
    return json.loads(PARAMETERS.read_text())


def layout(p):
    """Installation frame: pot body front Z=0, positive Z toward outside."""
    m, pot, k, b = (p[key] for key in ('plate', 'potentiometer', 'knob', 'back_panel'))
    for key in ('plate', 'potentiometer', 'knob', 'back_panel', 'anti_rotation'):
        for name, value in p[key].items():
            if name.endswith('_mm') and (not math.isfinite(value) or value < 0):
                raise ValueError('Dimensions must be finite and nonnegative: '+name)
    t = m['thickness_mm']
    wood_inner = t+m['seal_thickness_mm']
    wood_outer = wood_inner+b['thickness_mm']
    shaft_end = pot['thread_length_mm']+pot['shaft_above_thread_mm']
    stem_tip = shaft_end-k['shaft_engagement_mm']
    face_inner = wood_outer+k['face_to_wood_gap_mm']
    knob_outer = face_inner+k['face_thickness_mm']
    stem_length = face_inner-stem_tip
    print_height = k['face_thickness_mm']+stem_length
    bore_depth = k['shaft_engagement_mm']+k['bore_tip_clearance_mm']
    holes = [(0, sign*m['screw_pitch_y_mm']/2) for sign in (-1, 1)]
    available = p['installation']['available_width_mm']
    wall = m['minimum_wall_mm']
    if not (math.isfinite(available) and available >= m['width_mm']
            and min(m['width_mm'], m['height_mm'], t) > 0
            and 0 < m['corner_radius_mm'] < min(m['width_mm'], m['height_mm'])/2):
        raise ValueError('Invalid plate dimensions or available width')
    if not (pot['shaft_profile'] in ('round', 'd', 'splined')
            and 0 < pot['shaft_diameter_min_mm'] <= pot['shaft_diameter_mm'] <= pot['shaft_diameter_max_mm']
            and 0 < pot['shaft_diameter_mm'] <= k['bore_diameter_mm'] < k['stem_diameter_mm']
            and (pot['shaft_profile'] != 'd' or 0 < pot['shaft_flat_depth_mm'] < pot['shaft_diameter_mm']/2)
            and pot['shaft_diameter_mm'] <= pot['thread_diameter_mm'] < m['thread_hole_diameter_mm']
            and m['thread_hole_diameter_mm'] < pot['washer_outer_diameter_mm']
            and m['thread_hole_diameter_mm'] < pot['nut_max_diameter_mm']*math.cos(math.pi/6)
            and m['thread_hole_diameter_mm'] < pot['body_diameter_mm']):
        raise ValueError('Invalid shaft profile or bushing, washer, nut and bore diameters')
    if not (t+pot['washer_thickness_mm']+pot['nut_thickness_mm'] <= pot['thread_length_mm']
            and pot['nut_thickness_mm'] > 0):
        raise ValueError('Full nut cannot engage after plate and washer')
    if not (max(pot['nut_max_diameter_mm'], pot['washer_outer_diameter_mm']) < b['opening_diameter_mm']
            and k['stem_diameter_mm']+2*k['root_flare_radial_mm'] < b['opening_diameter_mm']
            and k['face_diameter_mm'] > b['opening_diameter_mm']
            and k['face_to_wood_gap_mm'] > 0):
        raise ValueError('Nut, washer, stem or face does not clear straight wood opening')
    if not (0 < k['shaft_engagement_mm'] and stem_length > k['root_flare_height_mm'] > 0
            and stem_tip-pot['thread_length_mm'] >= k['minimum_bushing_gap_mm']-1e-8
            and print_height-bore_depth >= k['minimum_wall_mm']
            and (k['stem_diameter_mm']-k['bore_diameter_mm'])/2 >= k['minimum_wall_mm']
            and k['face_thickness_mm'] > 0):
        raise ValueError('Insufficient stem wall, bore roof, engagement or bushing clearance')
    if not (0 < m['wood_pilot_diameter_mm'] < m['screw_hole_diameter_mm']
            and 0 < m['wood_pilot_depth_mm'] < b['thickness_mm']):
        raise ValueError('Wood pilots must remain blind')
    for x, y in holes:
        r = max(m['screw_hole_diameter_mm'], m['assumed_screw_head_diameter_mm'])/2
        if (min(m['width_mm']/2-abs(x), m['height_mm']/2-abs(y)) < r
                or abs(y) < pot['body_diameter_mm']/2+r+wall):
            raise ValueError('Screw head lacks edge or assumed pot-body clearance')
    a = p['anti_rotation']
    if a['enabled']:
        if (min(a['slot_width_mm'], a['slot_radial_length_mm']) <= 0
                or a['lug_center_radius_mm']-a['slot_radial_length_mm']/2 < m['thread_hole_diameter_mm']/2+wall
                or a['lug_center_radius_mm']+a['slot_radial_length_mm']/2 > m['height_mm']/2-wall
                or a['slot_width_mm']/2 > m['width_mm']/2-wall):
            raise ValueError('Optional stop-lug slot lacks surrounding plate material')
    count = k['grip_groove_count']
    if not (isinstance(count, int) and count >= 8 and count % 4 == 0
            and 0 < k['grip_groove_center_offset_mm'] < k['grip_groove_radius_mm']
            and k['grip_groove_radius_mm'] < k['face_diameter_mm']/2*math.sin(math.pi/count)):
        raise ValueError('Grip grooves must be discrete shallow recesses')
    return dict(wood_inner_z_mm=wood_inner, wood_outer_z_mm=wood_outer,
                thread_end_z_mm=pot['thread_length_mm'], shaft_end_z_mm=shaft_end,
                shaft_tip_beyond_wood_mm=shaft_end-wood_outer,
                knob_stem_tip_z_mm=stem_tip, knob_face_inner_z_mm=face_inner,
                knob_outer_z_mm=knob_outer, stem_length_mm=stem_length,
                knob_print_height_mm=print_height, bore_depth_mm=bore_depth,
                bore_roof_mm=print_height-bore_depth,
                knob_projection_mm=knob_outer-wood_outer,
                knob_bushing_gap_mm=stem_tip-pot['thread_length_mm'],
                shaft_bore_diametral_clearance_min_mm=k['bore_diameter_mm']-pot['shaft_diameter_max_mm'],
                shaft_bore_diametral_clearance_max_mm=k['bore_diameter_mm']-pot['shaft_diameter_min_mm'],
                screw_centers_mm=holes, side_clearance_mm=(available-m['width_mm'])/2)


def build_plate(p):
    d, m = layout(p), p['plate']
    w, h, t, r = (m[key] for key in ('width_mm', 'height_mm', 'thickness_mm', 'corner_radius_mm'))
    shape = Part.makeBox(w-2*r, h, t, V(-w/2+r, -h/2, 0)).fuse(
        Part.makeBox(w, h-2*r, t, V(-w/2, -h/2+r, 0)))
    for x in (-w/2+r, w/2-r):
        for y in (-h/2+r, h/2-r):
            shape = shape.fuse(Part.makeCylinder(r, t, V(x, y, 0)))
    shape = shape.cut(Part.makeCylinder(m['thread_hole_diameter_mm']/2, t+2, V(0, 0, -1)))
    for x, y in d['screw_centers_mm']:
        shape = shape.cut(Part.makeCylinder(m['screw_hole_diameter_mm']/2, t+2, V(x, y, -1)))
    a = p['anti_rotation']
    if a['enabled']:
        shape = shape.cut(Part.makeBox(a['slot_width_mm'], a['slot_radial_length_mm'], t+2,
                          V(-a['slot_width_mm']/2, a['lug_center_radius_mm']-a['slot_radial_length_mm']/2, -1)))
    shape = shape.removeSplitter()
    for x, y in d['screw_centers_mm']:
        r = m['screw_hole_diameter_mm']/2
        ring = Part.makeCylinder(r+m['minimum_wall_mm'], t, V(x, y, 0)).cut(
            Part.makeCylinder(r, t, V(x, y, 0)))
        if ring.cut(shape).Volume > 1e-6:
            raise ValueError('Screw passage lacks continuous surrounding material')
    return require_single(shape)


def shaft_prism(p, diameter, start, length, hole=False):
    # Splined shafts use the measured major-diameter envelope and a trial round
    # bore until tooth geometry is known; this is not a matching spline model.
    shape = Part.makeCylinder(diameter/2, length, V(0, 0, start))
    pot, k = p['potentiometer'], p['knob']
    if pot['shaft_profile'] == 'd':
        flat = pot['shaft_diameter_mm']/2-pot['shaft_flat_depth_mm']
        if hole:
            flat += k['bore_flat_clearance_mm']
        shape = shape.cut(Part.makeBox(diameter+2, diameter+2, length+2,
                                      V(flat, -diameter/2-1, start-1)))
    return shape


def build_knob(p):
    """Front face on bed; stem and blind coupling bore rise upward."""
    d, k = layout(p), p['knob']
    radius, t, stem = k['face_diameter_mm']/2, k['face_thickness_mm'], k['stem_diameter_mm']/2
    shape = Part.makeCylinder(radius, t)
    count = k['grip_groove_count']
    for i in range(count):
        angle = 2*math.pi*(i+0.5)/count
        rr = radius+k['grip_groove_center_offset_mm']
        shape = shape.cut(Part.makeCylinder(k['grip_groove_radius_mm'], t+2,
                         V(rr*math.cos(angle), rr*math.sin(angle), -1)))
    shape = shape.fuse(Part.makeCylinder(stem, d['stem_length_mm']+0.1, V(0, 0, t-0.1)))
    shape = shape.fuse(Part.makeCone(stem+k['root_flare_radial_mm'], stem,
                                    k['root_flare_height_mm'], V(0, 0, t)))
    bore_start = d['knob_print_height_mm']-d['bore_depth_mm']
    shape = shape.cut(shaft_prism(p, k['bore_diameter_mm'], bore_start, d['bore_depth_mm']+1, hole=True))
    return require_single(shape.removeSplitter())


def require_single(shape):
    if not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError('Each exported part must be one valid solid')
    return shape


def installed_knob(shape, p):
    # Rotation, not mirroring: printed +Z points toward the cabinet after fitting.
    result = shape.copy()
    result.Placement = App.Placement(V(0, 0, layout(p)['knob_outer_z_mm']), App.Rotation(V(1, 0, 0), 180))
    return result


def fixtures(p):
    """Unsaved ideal fixtures; actual PCB, threads, splines and wire paths unknown."""
    d, m, pot = layout(p), p['plate'], p['potentiometer']
    z = d['wood_inner_z_mm']
    wood = Part.makeBox(60, 56, p['back_panel']['thickness_mm'], V(-30, -28, z)).cut(
        Part.makeCylinder(p['back_panel']['opening_diameter_mm']/2, p['back_panel']['thickness_mm']+2, V(0, 0, z-1)))
    for x, y in d['screw_centers_mm']:
        wood = wood.cut(Part.makeCylinder(m['wood_pilot_diameter_mm']/2, m['wood_pilot_depth_mm'], V(x, y, z)))
    body = Part.makeCylinder(pot['body_diameter_mm']/2, pot['body_depth_mm'], V(0, 0, -pot['body_depth_mm']))
    bush = Part.makeCylinder(pot['thread_diameter_mm']/2, pot['thread_length_mm'])
    shaft = shaft_prism(p, pot['shaft_diameter_mm'], pot['thread_length_mm'], pot['shaft_above_thread_mm'])
    # User measured maximum nut diameter, not across-flats: vertices lie on Ø11.
    radius = pot['nut_max_diameter_mm']/2
    vertices = [V(radius*math.cos(i*math.pi/3), radius*math.sin(i*math.pi/3),
                  m['thickness_mm']+pot['washer_thickness_mm']) for i in range(6)]
    nut = Part.Face(Part.makePolygon(vertices+[vertices[0]])).extrude(V(0, 0, pot['nut_thickness_mm']))
    washer = Part.makeCylinder(pot['washer_outer_diameter_mm']/2, pot['washer_thickness_mm'], V(0, 0, m['thickness_mm']))
    cutter = Part.makeCylinder(m['thread_hole_diameter_mm']/2, 30, V(0, 0, -1))
    return dict(Wood=wood, PotBody=body, Bushing=bush, Shaft=shaft,
                Washer=washer.cut(cutter), Nut=nut.cut(cutter))


def verify_fit(p):
    plate, knob = build_plate(p), installed_knob(build_knob(p), p)
    f = fixtures(p)
    for name, shape in f.items():
        if plate.common(shape).Volume > 1e-6 or knob.common(shape).Volume > 1e-6:
            raise ValueError('Printed part intersects nominal fixture: '+name)
    if plate.common(knob).Volume > 1e-6:
        raise ValueError('Plate and knob interfere')
    for name in ('Nut', 'Washer', 'Bushing', 'Shaft'):
        if f['Wood'].common(f[name]).Volume > 1e-6:
            raise ValueError('Straight wood bore intersects fixture: '+name)
    d = layout(p)
    return dict(nominal_fixture_clear=True, knob_projection_mm=d['knob_projection_mm'],
                shaft_tip_beyond_wood_mm=d['shaft_tip_beyond_wood_mm'],
                shaft_engagement_mm=p['knob']['shaft_engagement_mm'],
                knob_bushing_gap_mm=d['knob_bushing_gap_mm'],
                shaft_profile=p['potentiometer']['shaft_profile'],
                spline_geometry_modeled=False,
                bore_profile='d' if p['potentiometer']['shaft_profile'] == 'd' else 'round_trial',
                shaft_bore_diametral_clearance_mm=[d['shaft_bore_diametral_clearance_min_mm'], d['shaft_bore_diametral_clearance_max_mm']],
                actual_shaft_fit_and_torque_verified=False,
                scope='Static ideal fixtures only; actual shaft/profile, printing, PCB/wires, strength and sealing unverified')


def mesh_volume(mesh):
    vertices, triangles = mesh.Topology
    return sum(vertices[a].dot(vertices[b].cross(vertices[c])) for a, b, c in triangles)/6


def verify_exports(output=OUTPUT, p=None):
    output, p = Path(output), load_parameters() if p is None else p
    results = {}
    for name, expected in (('Plate', build_plate(p)), ('Knob', build_knob(p))):
        stem = PARTS[name]
        doc = App.openDocument(str(output/(stem+'.FCStd')))
        try:
            if len(doc.Objects) != 1 or json.loads(doc.getObject(name).DesignJSON) != p:
                raise ValueError('Independent document must have one part and matching parameter snapshot')
            step = Part.Shape()
            step.read(str(output/(stem+'.step')))
            for shape in (doc.getObject(name).Shape, step):
                require_single(shape)
                if shape.cut(expected).Volume+expected.cut(shape).Volume > 1e-6:
                    raise ValueError('Saved CAD/STEP differs from generated part: '+name)
            mesh = Mesh.Mesh(str(output/(stem+'.stl')))
            volume = mesh_volume(mesh)
            if (not mesh.isSolid() or mesh.countComponents() != 1 or mesh.hasNonManifolds()
                    or mesh.hasSelfIntersections() or volume <= 0 or abs(volume-expected.Volume) > 0.05):
                raise ValueError('STL topology or volume mismatch: '+name)
            bounds = expected.optimalBoundingBox(False)
            for key in ('XMin', 'YMin', 'ZMin', 'XMax', 'YMax', 'ZMax'):
                if abs(getattr(mesh.BoundBox, key)-getattr(bounds, key)) > 0.005:
                    raise ValueError('STL print bounds differ: '+name)
            results[name] = dict(passed=True, solid_count=1, saved_cad_step_match=True,
                                 closed_mesh=True, mesh_components=1, mesh_self_intersections=False,
                                 mesh_nonmanifold_edges=False, mesh_triangles=mesh.CountFacets,
                                 cad_volume_mm3=expected.Volume, mesh_volume_mm3=volume)
        finally:
            App.closeDocument(doc.Name)
    return dict(passed=True, parts=results, installation=verify_fit(p))


def prepare_view(doc):
    import FreeCADGui as Gui
    doc.recompute()
    view = Gui.getDocument(doc.Name).activeView()
    view.stopAnimating()
    view.setAnimationEnabled(False)
    view.viewAxonometric()
    view.fitAll()
    Gui.updateGui()
    return view


def render_section(p, output):
    import FreeCADGui as Gui
    doc = App.newDocument('LEDPotControlsTemporarySection')
    try:
        shapes = fixtures(p)
        shapes.update(Plate=build_plate(p), Knob=installed_knob(build_knob(p), p))
        half = Part.makeBox(100, 100, 100, V(0, -50, -40))
        colors = dict(Wood=(0.66, 0.45, 0.28), Plate=(0.88, 0.39, 0.16),
                      PotBody=(0.24, 0.29, 0.34), Knob=(0.12, 0.38, 0.55))
        for name, shape in shapes.items():
            obj = doc.addObject('Part::Feature', name)
            obj.Shape = shape.common(half)
            obj.ViewObject.ShapeColor = colors.get(name, (0.67, 0.70, 0.73))
            obj.ViewObject.DisplayMode = 'Flat Lines'
        view = prepare_view(doc)
        view.setCameraOrientation(App.Rotation(V(0, 0, 1), V(0, 1, 0), V(-1, 0, 0), 'ZXY').Q)
        view.fitAll()
        Gui.updateGui()
        view.saveImage(str(output/'installation-section.png'), 1400, 1000, 'White')
    finally:
        App.closeDocument(doc.Name)


def export(output=OUTPUT):
    if not App.GuiUp:
        raise RuntimeError('Run tools/build-led-pot-mount.FCMacro in the FreeCAD GUI')
    output = Path(output)
    targets = [(output/(stem+'.FCStd')).resolve() for stem in PARTS.values()]
    for doc in App.listDocuments().values():
        if doc.Name in ('LEDPotPlatePrint', 'LEDPotKnobPrint') or (doc.FileName and Path(doc.FileName).resolve() in targets):
            raise RuntimeError('Close target plate and knob first; preserve manual edits separately')
    p = load_parameters()
    verify_fit(p)
    output.mkdir(parents=True, exist_ok=True)
    shapes = {'Plate': build_plate(p), 'Knob': build_knob(p)}
    for name, shape in shapes.items():
        doc = App.newDocument('LEDPot'+name+'Print')
        try:
            obj = doc.addObject('Part::Feature', name)
            obj.Label = {'Plate': '灯带电位器固定平板 · 独立试装', 'Knob': '灯带旋钮 · 内伸轴套 · 独立试装'}[name]
            obj.Shape = shape
            obj.addProperty('App::PropertyString', 'DesignJSON', 'Design').DesignJSON = json.dumps(p, ensure_ascii=False)
            obj.addProperty('App::PropertyString', 'ParameterSource', 'Design').ParameterSource = 'cad/led-pot-mount.json; edit JSON and rebuild'
            obj.setEditorMode('DesignJSON', 1)
            obj.setEditorMode('ParameterSource', 1)
            obj.ViewObject.Visibility = True
            obj.ViewObject.ShapeColor = (0.88, 0.39, 0.16) if name == 'Plate' else (0.12, 0.38, 0.55)
            obj.ViewObject.LineColor = (0.12, 0.16, 0.20)
            obj.ViewObject.DisplayMode = 'Flat Lines'
            stem = PARTS[name]
            MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.001, AngularDeflection=0.025,
                                   Relative=False).write(str(output/(stem+'.stl')))
            Part.export([obj], str(output/(stem+'.step')))
            view = prepare_view(doc)
            view.saveImage(str(output/(name.lower()+'-preview.png')), 1200, 1000, 'White')
            doc.saveAs(str(output/(stem+'.FCStd')))
        finally:
            App.closeDocument(doc.Name)
    render_section(p, output)
    names = [stem+ext for stem in PARTS.values() for ext in ('.FCStd', '.step', '.stl')]
    names += ['plate-preview.png', 'knob-preview.png', 'installation-section.png']
    data = dict(units='mm', parameters=p, derived=layout(p), quantity_per_part=1,
                print_envelopes_mm={name: [getattr(shape.optimalBoundingBox(False), key) for key in ('XLength', 'YLength', 'ZLength')]
                                    for name, shape in shapes.items()},
                print_orientation='Plate flat at Z=0; knob front face at Z=0, stem/bore upward. No supports in nominal geometry; inspect slice.',
                validation=verify_exports(output, p),
                source_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in (PARAMETERS, Path(__file__))},
                files_sha256={name: hashlib.sha256((output/name).read_bytes()).hexdigest() for name in names})
    (output/REPORT).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    return data


def package(output=OUTPUT):
    output = Path(output)
    names = [stem+ext for stem in PARTS.values() for ext in ('.FCStd', '.step', '.stl')]
    names += [REPORT, 'README.md', 'plate-preview.png', 'knob-preview.png', 'installation-section.png']
    paths = [output/name for name in names]+[PARAMETERS, Path(__file__), ROOT/'tools/build-led-pot-mount.FCMacro', ROOT/'tests/test_led_pot_mount.py']
    target = output.parent/'led-pot-flat-controls-trial-print-package.zip'
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, str(path.relative_to(ROOT)))
    return target


if __name__ == '__main__':
    export()
    package()
