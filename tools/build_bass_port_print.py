"""Independent externally inserted D port; clock positions viewed from outside."""
import hashlib
import json
import math
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

import FreeCAD as App
import Mesh
import MeshPart
import Part

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'cad/bass-port-print.json'
OUTPUT = ROOT / 'output/3d-print/bass-port'
V = App.Vector
STEMS = {'BassPort': 'Bass-port-D25', 'FitCoupon': 'Bass-port-fit-coupon'}
# 10 o'clock, seen from outside: upper left in installed XZ coordinates.
RELIEF_NORMAL = V(-math.sqrt(3) / 2, 0, 0.5)


def load_config():
    return json.loads(CONFIG.read_text())


def datums(config):
    m, t = config['measured'], config['trial']
    radius = m['tube_outer_diameter'] / 2
    return dict(radius=radius, top=m['tube_outer_height'] - radius,
                bevel=radius - t['clock10_radial_relief'], wall=m['wall_thickness'])


def screw_centers(config):
    t = config['trial']
    radius = t['screw_pitch_diameter'] / 2
    return [(radius * math.cos(math.radians(t['screw_start_angle_deg'] + i * 90)),
             radius * math.sin(math.radians(t['screw_start_angle_deg'] + i * 90)))
            for i in range(t['screw_count'])]


def estimate_length(config, bore_area):
    """Equal net volume/Fb; equal-area circular end correction is approximate."""
    reference = config['length_estimate']
    diameter = reference['reference_round_bore_diameter']
    length = reference['reference_round_physical_length']
    coefficient = reference['end_correction_coefficient']
    equivalent = math.sqrt(4 * bore_area / math.pi)
    area_ratio = bore_area / (math.pi * diameter**2 / 4)
    old_effective = length + coefficient * diameter
    new_effective = old_effective * area_ratio
    return dict(reference_round_bore_diameter_mm=diameter,
                reference_round_physical_length_mm=length,
                area_ratio=area_ratio,
                reference_effective_length_mm=old_effective,
                estimated_effective_length_mm=new_effective,
                estimated_physical_length_mm=new_effective - coefficient * equivalent,
                selected_physical_length_mm=config['trial']['total_length'],
                assumptions=reference['assumption'])


def validate_config(config):
    m, t = config['measured'], config['trial']
    if config['units'] != 'mm' or config['installation_released'] is not False:
        raise ValueError('Expected mm and unreleased trial installation')
    dimensions = list(m.values()) + [value for key, value in t.items()
                                    if key not in ('screw_start_angle_deg', 'entrance_transition_start_y', 'printer_volume')]
    dimensions += [value for key, value in config['length_estimate'].items() if key != 'assumption']
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0
           for value in dimensions):
        raise ValueError('Dimensions must be positive and finite')
    d = datums(config)
    if not 2 * d['wall'] < m['tube_outer_height'] < 2 * d['radius']:
        raise ValueError('D section must retain an open bore and a flat top')
    if d['radius'] <= d['wall'] or d['bevel'] <= d['wall']:
        raise ValueError('Relief consumes the bore')
    if m['tube_outer_diameter'] > m['panel_hole_diameter']:
        raise ValueError('Tube exceeds the nominal opening reference')
    if not m['screw_shank_diameter'] <= t['screw_hole_diameter'] < m['screw_head_diameter']:
        raise ValueError('Screw passage must admit nominal shank and retain head')
    if not t['countersink_depth'] <= t['base_thickness'] - 1:
        raise ValueError('Countersink must leave at least 1 mm base below cone')
    if t['base_diameter'] <= m['panel_hole_diameter'] + 6:
        raise ValueError('Base must cover the complete round wood hole with seal land')
    if min(t['total_length'], t['coupon_total_length']) <= t['base_thickness'] + m['panel_thickness'] + 2 * t['mouth_fillet_radius']:
        raise ValueError('Both bodies need a D segment beyond the measured panel and mouth fillet')
    if t['mouth_fillet_radius'] > min(d['wall'] / 2, t['base_thickness'] / 2):
        raise ValueError('Mouth fillet must retain at least half the nominal lip thickness')
    start = t['entrance_transition_start_y']
    if not math.isfinite(start) or not -t['base_thickness'] + t['mouth_fillet_radius'] < start <= 0:
        raise ValueError('Airway transition must begin inside the base after the exterior mouth fillet')
    if len(t['printer_volume']) != 3 or any(not math.isfinite(v) or v <= 0 for v in t['printer_volume']):
        raise ValueError('Expected three positive printer dimensions')
    if t['screw_count'] != 4:
        raise ValueError('Four equally spaced screw holes required')
    if not math.isfinite(t['screw_start_angle_deg']) or not 0 <= t['screw_start_angle_deg'] < 360:
        raise ValueError('Screw start angle must be finite and within [0, 360)')
    centers = screw_centers(config)
    for i, center in enumerate(centers):
        if len(center) != 2 or any(not math.isfinite(v) for v in center):
            raise ValueError('Screw centers must be finite XZ pairs')
        radial = math.hypot(*center)
        hole_r = t['screw_hole_diameter'] / 2
        if radial - hole_r < m['panel_hole_diameter'] / 2 + 2:
            raise ValueError('Screw must enter wood outside the round opening')
        if radial + hole_r + 2 > t['base_diameter'] / 2:
            raise ValueError('Insufficient base material outside screw hole')
        head_r = m['screw_head_diameter'] / 2
        if radial + head_r + 1 > t['base_diameter'] / 2:
            raise ValueError('Insufficient base rim outside countersink')
        if radial - head_r < max(m['panel_hole_diameter'] / 2, d['radius']) + 1:
            raise ValueError('Countersink approaches the collar or opening')
        if any(math.dist(center, other) <= t['screw_hole_diameter'] + 2 for other in centers[:i]):
            raise ValueError('Screw holes overlap')


def bevel_cutter(distance, start_y, length):
    """Extruded half-space n dot (X,Z) > distance; no facet approximation."""
    n = RELIEF_NORMAL
    tangent = V(n.z, 0, -n.x)
    points = [n * a + tangent * b + V(0, start_y, 0)
              for a, b in ((distance, -100), (100, -100), (100, 100), (distance, 100))]
    return Part.Face(Part.makePolygon(points + [points[0]])).extrude(V(0, length, 0))


def profile_prism(config, length, start_y=0, inside=False):
    d = datums(config)
    offset = d['wall'] if inside else 0
    radius, top, bevel = d['radius'] - offset, d['top'] - offset, d['bevel'] - offset
    shape = Part.makeCylinder(radius, length, V(0, start_y, 0), V(0, 1, 0))
    shape = shape.cut(Part.makeBox(200, length + 2, 100, V(-100, start_y - 1, top)))
    return shape.cut(bevel_cutter(bevel, start_y - 1, length + 2)).removeSplitter()


def end_face(shape, y):
    return next(face for face in shape.Faces
                if isinstance(face.Surface, Part.Plane)
                and all(abs(vertex.Point.y - y) < 1e-6 for vertex in face.Vertexes))


def round_wire(radius, y):
    return Part.Wire(Part.makeCircle(radius, V(0, y, 0), V(0, 1, 0)))


def airway(config, insertion):
    """Circular exterior mouth, gradual contraction inside wood, then D throat."""
    t, m, d = config['trial'], config['measured'], datums(config)
    start, end = t['entrance_transition_start_y'], m['panel_thickness']
    radius = d['radius'] - d['wall']
    circle = round_wire(radius, start)
    d_wire = end_face(profile_prism(config, 1, end, inside=True), end).OuterWire
    transition = Part.makeLoft([circle, d_wire], True, False)
    if not transition.isValid() or len(transition.Solids) != 1:
        raise ValueError('Circular-to-D airway transition must be a valid solid')
    front = -t['base_thickness'] - 1
    opening = Part.makeCylinder(radius, start - front, V(0, front, 0), V(0, 1, 0))
    opening = opening.fuse(transition).fuse(profile_prism(config, insertion - end + 1, end, inside=True))
    return opening.removeSplitter()


def rounded_mouths(shape, config, insertion):
    """Round only the two airway rims; keep OD, base and sealing face datums."""
    t, d = config['trial'], datums(config)
    front_y = -t['base_thickness']
    front_wire = round_wire(d['radius'] - d['wall'], front_y)
    rear_wire = end_face(profile_prism(config, 1, insertion, inside=True), insertion).OuterWire
    edges = []
    for y, wire in [(front_y, front_wire), (insertion, rear_wire)]:
        matching = [edge for edge in shape.Edges
                    if all(abs(vertex.Point.y - y) < 1e-6 for vertex in edge.Vertexes)
                    and abs(edge.common(wire).Length - edge.Length) < 1e-6]
        if not matching:
            raise ValueError('Airway mouth edge not found; refusing to skip fillet')
        edges.extend(matching)
    return shape.makeFillet(t['mouth_fillet_radius'], edges).removeSplitter()


def mouth_area(shape, y):
    """Choose the smallest planar boundary enclosing the airway axis."""
    face = end_face(shape, y)
    areas = [Part.Face(wire).Area for wire in face.Wires
             if Part.Face(wire).isInside(V(0, y, 0), 1e-6, True)]
    return min(areas)


def print_shape(installed):
    """Rigid rotation, never reflection: exterior base face on bed, tube upward."""
    shape = installed.copy()
    shape.rotate(V(), V(1, 0, 0), 90)
    box = shape.optimalBoundingBox(False)
    shape.translate(V(-box.XMin, -box.YMin, -box.ZMin))
    return shape


def build(config=None):
    config = config or load_config()
    validate_config(config)
    t, m, d = config['trial'], config['measured'], datums(config)
    result = {}
    outer = profile_prism(config, 1)
    bore = profile_prism(config, 1, inside=True)
    for name, length in [('BassPort', t['total_length']), ('FitCoupon', t['coupon_total_length'])]:
        insertion = length - t['base_thickness']
        collar = Part.makeCylinder(d['radius'], m['panel_thickness'], V(), V(0, 1, 0))
        tube = collar.fuse(profile_prism(config, insertion - m['panel_thickness'], m['panel_thickness']))
        base = Part.makeCylinder(t['base_diameter'] / 2, t['base_thickness'],
                                 V(0, -t['base_thickness'], 0), V(0, 1, 0))
        shape = tube.fuse(base).cut(airway(config, insertion))
        for x, z in screw_centers(config):
            shape = shape.cut(Part.makeCylinder(t['screw_hole_diameter'] / 2,
                                               t['base_thickness'] + 2,
                                               V(x, -t['base_thickness'] - 1, z), V(0, 1, 0)))
            shape = shape.cut(Part.makeCone(m['screw_head_diameter'] / 2,
                                           t['screw_hole_diameter'] / 2,
                                           t['countersink_depth'],
                                           V(x, -t['base_thickness'], z), V(0, 1, 0)))
        shape = rounded_mouths(shape.removeSplitter(), config, insertion)
        if not shape.isValid() or len(shape.Solids) != 1:
            raise ValueError('Each part must be one valid connected solid')
        printable = print_shape(shape)
        box = printable.optimalBoundingBox(False)
        size = [box.XLength, box.YLength, box.ZLength]
        if any(a > b for a, b in zip(size, t['printer_volume'])):
            raise ValueError('Print part exceeds configured printer volume')
        result[name] = dict(installed=shape, printable=printable, print_size_mm=size,
                            total_length_mm=length, insertion_length_mm=insertion,
                            chamber_protrusion_mm=insertion - m['panel_thickness'],
                            round_collar_length_mm=m['panel_thickness'],
                            round_collar_outer_diameter_mm=m['tube_outer_diameter'],
                            exterior_mouth_area_mm2=mouth_area(shape, -t['base_thickness']),
                            interior_mouth_area_mm2=mouth_area(shape, insertion))
    return result, dict(outer_section_area_mm2=outer.Volume, bore_area_mm2=bore.Volume,
                        equivalent_round_bore_diameter_mm=math.sqrt(4 * bore.Volume / math.pi),
                        outer_tube_width_mm=outer.optimalBoundingBox(False).XLength,
                        outer_tube_height_mm=outer.optimalBoundingBox(False).ZLength,
                        bore_height_mm=bore.optimalBoundingBox(False).ZLength,
                        area_ratio_to_original_32mm_bore=bore.Volume / (math.pi * 16**2),
                        length_estimate=estimate_length(config, bore.Volume),
                        current_acoustic_tuning_verified=False,
                        constant_section_length_estimate_applies_to_current_airway=False,
                        countersink=dict(entrance_diameter_mm=m['screw_head_diameter'],
                                         depth_mm=t['countersink_depth'],
                                         passage_diameter_mm=t['screw_hole_diameter'],
                                         remaining_base_mm=t['base_thickness'] - t['countersink_depth'],
                                         included_angle_deg=math.degrees(2 * math.atan(
                                             (m['screw_head_diameter'] - t['screw_hole_diameter'])
                                             / (2 * t['countersink_depth'])))),
                        screw_centers_outside_xz_mm=screw_centers(config))


def verify_installation(config, part):
    """Temporary nominal-hole and provisional-obstacle fixtures, never saved."""
    t, m, d = config['trial'], config['measured'], datums(config)
    length = part['insertion_length_mm']
    panel = Part.makeBox(100, m['panel_thickness'], 100, V(-50, 0, -50)).cut(
        Part.makeCylinder(m['panel_hole_diameter'] / 2, m['panel_thickness'] + 2,
                          V(0, -1, 0), V(0, 1, 0)))
    # The screws are not inserted during the axial installation check.
    roof = Part.makeBox(100, length + 2, 50, V(-50, m['panel_thickness'], d['top'] + 0.2))
    post = bevel_cutter(d['bevel'] + 0.2, m['panel_thickness'], length)
    shape = part['installed']
    for retreat in (0, 0.1, 1, 4, 12, 24, 50, 100, 160, 200):
        moved = shape.copy()
        moved.translate(V(0, -retreat, 0))
        for fixture in (panel, roof, post):
            if moved.common(fixture).Volume > 1e-6:
                raise ValueError('Axial insertion overlaps assumed fixture')
    # Verify all space in the circular hole is sealed by the base except the bore.
    disk = Part.makeCylinder(m['panel_hole_diameter'] / 2, t['base_thickness'],
                             V(0, -t['base_thickness'], 0), V(0, 1, 0))
    # Fillets enlarge only the intended airway at the two mouths. Build its
    # actual exterior boundary so the sealing check cannot mask a separate leak.
    face = end_face(shape, -t['base_thickness'])
    opening_wire = min((wire for wire in face.Wires if Part.Face(wire).isInside(V(0, -t['base_thickness'], 0), 1e-6, True)),
                       key=lambda wire: Part.Face(wire).Area)
    bore = Part.Face(opening_wire).extrude(V(0, t['base_thickness'], 0))
    leakage = disk.cut(shape.fuse(bore)).Volume
    if leakage > 1e-6:
        raise ValueError('Base leaves an unintended opening in the round wood hole')
    return dict(round_hole_and_assumed_obstacles_clear=True,
                outside_axial_path_clear=True, unused_round_opening_covered=True,
                unintended_opening_volume_mm3=leakage, actual_post_verified=False,
                round_collar_length_mm=m['panel_thickness'],
                fixtures='Nominal 38 mm opening reference; top +0.2 mm; provisional clock10 plane +0.2 mm; real hole clearance unmeasured')


def mesh_volume(mesh):
    vertices, triangles = mesh.Topology
    origin = mesh.BoundBox.Center
    return math.fsum((vertices[a] - origin).dot((vertices[b] - origin).cross(vertices[c] - origin)) / 6
                     for a, b, c in triangles)


def verify_exports(output, config, parts):
    result = {}
    for name, part in parts.items():
        stem, expected = STEMS[name], part['printable']
        doc = App.openDocument(str(Path(output) / (stem + '.FCStd')))
        try:
            objects = [obj for obj in doc.Objects if obj.TypeId == 'Part::Feature']
            if len(objects) != 1:
                raise ValueError('Only one printable body per file')
            saved = objects[0].Shape
            step = Part.Shape()
            step.read(str(Path(output) / (stem + '.step')))
            for shape in (saved, step):
                if not shape.isValid() or len(shape.Solids) != 1:
                    raise ValueError('Saved CAD/STEP must be one valid solid')
                if max(shape.cut(expected).Volume, expected.cut(shape).Volume) > 1e-5:
                    raise ValueError('Saved CAD/STEP differs from generator')
            mesh = Mesh.Mesh(str(Path(output) / (stem + '.stl')))
            volume = mesh_volume(mesh)
            if (not mesh.isSolid() or mesh.countComponents() != 1 or volume <= 0
                    or mesh.hasNonManifolds() or mesh.hasSelfIntersections()):
                raise ValueError('STL must be one closed nonintersecting manifold')
            if abs(volume - expected.Volume) > max(0.1, expected.Volume * 0.0002):
                raise ValueError('STL volume differs from CAD')
            box = mesh.BoundBox
            mesh_size = [box.XLength, box.YLength, box.ZLength]
            # Require the independently read mesh envelope within 0.01 mm.
            if any(abs(a - b) > 0.01 for a, b in zip(mesh_size, part['print_size_mm'])):
                raise ValueError('STL dimensions differ from CAD')
            result[name] = dict(valid_solid=True, solid_count=1, cad_step_readback_match=True,
                                closed_mesh=True, mesh_components=1, self_intersections=False,
                                non_manifold=False, cad_volume_mm3=expected.Volume,
                                mesh_volume_mm3=volume,
                                mesh_relative_volume_error=abs(volume - expected.Volume) / expected.Volume,
                                mesh_relative_volume_error_limit=0.0002,
                                mesh_generator='FreeCAD Netgen: GrowthRate=0.15, SegPerEdge=10, SegPerRadius=32',
                                mesh_size_mm=mesh_size,
                                triangles=mesh.CountFacets,
                                installation=verify_installation(config, part))
        finally:
            App.closeDocument(doc.Name)
    return result


def dimensions_svg(config, parts, metrics):
    """Actual circular entrance, D throat and longitudinal solid section."""
    from xml.sax.saxutils import escape
    m, t = config['measured'], config['trial']
    part = parts['BassPort']
    shape = part['installed']
    paths = []

    def draw_wire(wire, cx, cy, scale, color, side=False):
        points = wire.discretize(Deflection=0.01)
        coords = [((cx + (point.y + t['base_thickness']) * scale) if side else cx + point.x * scale,
                   cy - point.z * scale) for point in points]
        path = 'M ' + ' L '.join(f'{x:.3f},{y:.3f}' for x, y in coords) + ' Z'
        return f'<path d="{path}" fill="{color}" stroke="#17383e" stroke-width="1.5"/>'

    face = end_face(shape, -t['base_thickness'])
    front_wire = min((wire for wire in face.Wires
                      if Part.Face(wire).isInside(V(0, -t['base_thickness'], 0), 1e-6, True)),
                     key=lambda wire: Part.Face(wire).Area)
    paths.append(draw_wire(front_wire, 270, 260, 7, '#fffdf8'))
    for inside, color in [(False, '#448fa0'), (True, '#fffdf8')]:
        wire = end_face(profile_prism(config, 1, inside=inside), 0).OuterWire
        paths.append(draw_wire(wire, 270, 750, 7, color))
    section = shape.common(Part.makeBox(0.1, 110, 100, V(-0.05, -10, -50)))
    for face in section.Faces:
        if isinstance(face.Surface, Part.Plane) and all(abs(vertex.Point.x + 0.05) < 1e-6 for vertex in face.Vertexes):
            for wire in face.Wires:
                paths.append(draw_wire(wire, 650, 750, 7, '#448fa0', side=True))
    notes = [
        '后置倒相管 · 圆形插接段 / D 型腔内段 / 双端圆角',
        f'后板实厚 {m["panel_thickness"]:g}；穿板外径 Ø{m["tube_outer_diameter"]:g}，按用户尺寸不再扣余量',
        'D 型外轮廓从后板内面开始，外高 25、直管名义壁厚 3',
        f'10 点方向退让 {t["clock10_radial_relief"]:g}；只在出板后的 D 型段生效',
        f'两端管口内缘 R{t["mouth_fillet_radius"]:g}，向内去料；腔内口边缘局部厚 1.5',
        f'气道在 Y={t["entrance_transition_start_y"]:g} 至 {m["panel_thickness"]:g} 逐渐由圆变 D；不留挡流台阶',
        f'D 型喉部 {metrics["bore_area_mm2"]:.1f} mm²；等面积圆孔 Ø{metrics["equivalent_round_bore_diameter_mm"]:.2f}',
        f'Ø60 × 4 基座；4 × Ø{t["screw_hole_diameter"]:g} 通孔／Ø7.5 深 {t["countersink_depth"]:g} 锥沉孔，PCD50 均布',
        f'总长 {part["total_length_mm"]:g}（含基座）；插入 {part["insertion_length_mm"]:g}；腔内伸 {part["chamber_protrusion_mm"]:g}',
        '短试装件总长 24；先试近孔安装，再检查长管全程净空',
        '打印：基座外表面贴床，管口朝上；圆角／收敛段需切片检查',
        '单位 mm、100%、勿镜像；密封、柱位、风噪和调谐待实测',
    ]
    labels = ''.join(f'<text x="570" y="{65+i*34}" font-size="{24 if i == 0 else 18}">{escape(note)}</text>'
                     for i, note in enumerate(notes))
    holes = ''.join(f'<circle cx="{270+x*7}" cy="{260-z*7}" r="{m["screw_head_diameter"]*3.5:g}" fill="#fffdf8" stroke="#17383e"/>'
                    f'<circle cx="{270+x*7}" cy="{260-z*7}" r="{t["screw_hole_diameter"]*3.5:g}" fill="none" stroke="#17383e" stroke-dasharray="3 3"/>'
                    for x, z in screw_centers(config))
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="1030" viewBox="0 0 1500 1030">'
            '<rect width="1500" height="1030" fill="#fffdf8"/>'
            '<g font-family="PingFang SC, sans-serif" fill="#17383e">'
            '<circle cx="270" cy="260" r="210" fill="#d5e2e4" stroke="#17383e" stroke-width="2"/>'
            '<circle cx="270" cy="260" r="133" fill="none" stroke="#b07b42" stroke-dasharray="8 5" stroke-width="2"/>'
            '<rect x="678" y="505" width="84" height="112" fill="#e5c69f"/>'
            '<rect x="678" y="883" width="84" height="112" fill="#e5c69f"/>'
            '<path d="M762 495 V1000" stroke="#b07b42" stroke-dasharray="5 5"/>'
            + holes + ''.join(paths)
            + '<text x="190" y="30" font-size="20">↑ 箱体上方</text>'
            '<text x="75" y="510" font-size="20">箱外正视：圆形入口已加圆角</text>'
            '<text x="75" y="550" font-size="18">虚线为 Ø38 穿板外径；四孔从箱外沉头</text>'
            '<text x="100" y="970" font-size="20">后板内面的 D 型喉部截面</text>'
            '<text x="650" y="480" font-size="20">中心纵剖：圆角与圆 → D 气道来自实际 CAD</text>'
            '<text x="780" y="535" font-size="18">虚线：12 mm 后板内面；D 型外段由此开始</text>'
            '<text x="1030" y="1000" font-size="18">左：箱外　　右：箱内 →</text>'
            + labels + '</g></svg>')


def export(output=OUTPUT):
    if not App.GuiUp:
        raise RuntimeError('Use tools/build-bass-port-print.FCMacro in the FreeCAD GUI')
    import FreeCADGui as Gui

    config = load_config()
    parts, metrics = build(config)
    output = Path(output)
    targets = {(output / (stem + '.FCStd')).resolve() for stem in STEMS.values()}
    if any(doc.FileName and Path(doc.FileName).resolve() in targets for doc in App.listDocuments().values()):
        raise RuntimeError('Close target port files and save manual edits separately before rebuilding')
    if 'BassPortPrint' in App.listDocuments():
        raise RuntimeError('Close BassPortPrint before rebuilding')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.bass-port-', dir=output.parent) as temporary:
        staged = Path(temporary)
        for name, data in parts.items():
            stem = STEMS[name]
            doc = App.newDocument('BassPortPrint')
            try:
                obj = doc.addObject('Part::Feature', name)
                obj.Label = 'D 型倒相管 · 25 mm 高 / 10 点斜面' if name == 'BassPort' else 'D 型倒相管 · 短试装件'
                obj.Shape = data['printable']
                obj.addProperty('App::PropertyString', 'ParametersJSON', 'Design').ParametersJSON = json.dumps(config, ensure_ascii=False, sort_keys=True)
                obj.ViewObject.Visibility = True
                obj.ViewObject.ShapeColor = (0.24, 0.56, 0.63)
                obj.ViewObject.LineColor = (0.08, 0.19, 0.22)
                obj.ViewObject.DisplayMode = 'Flat Lines'
                doc.recompute()
                # Netgen avoids self-intersecting triangles at the loft/fillet seams.
                mesh = MeshPart.meshFromShape(Shape=obj.Shape, GrowthRate=0.15,
                                              SegPerEdge=10, SegPerRadius=32,
                                              SecondOrder=0, Optimize=1, AllowQuad=0)
                mesh.write(str(staged / (stem + '.stl')))
                step = staged / (stem + '.step')
                Part.export([obj], str(step))
                step.write_text('\n'.join(line.rstrip() for line in step.read_text().splitlines()) + '\n')
                view = Gui.getDocument(doc.Name).activeView()
                view.stopAnimating()
                view.setAnimationEnabled(False)
                view.viewAxonometric()
                view.fitAll()
                Gui.updateGui()
                view.saveImage(str(staged / (stem + '.png')), 1400, 1100, 'White')
                doc.saveAs(str(staged / (stem + '.FCStd')))
            finally:
                App.closeDocument(doc.Name)
        report = dict(parameters=config, metrics=metrics,
                      parts={name: {key: value for key, value in part.items() if key not in ('installed', 'printable')}
                             for name, part in parts.items()},
                      validation=verify_exports(staged, config, parts),
                      source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      print_orientation='Exterior base face on Z=0; tube up; installed top points toward print -Y; rigid rotation only')
        (staged / 'Bass-port-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        (staged / 'dimensions.svg').write_text(dimensions_svg(config, parts, metrics))
        output.mkdir(parents=True, exist_ok=True)
        for path in staged.iterdir():
            path.replace(output / path.name)
    package(output)
    return report


def package(output=OUTPUT):
    """Refresh checksums and the independent print ZIP, excluding CAD backups."""
    output = Path(output)
    files = sorted(path for path in output.iterdir()
                   if path.suffix in ('.FCStd', '.step', '.stl', '.json', '.png', '.svg', '.md'))
    checksum = output / 'SHA256SUMS'
    checksum.write_text(''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n'
                               for path in files))
    target = output.parent / 'bass-port-D25-trial-print-package.zip'
    with tempfile.TemporaryDirectory(prefix='.bass-port-zip-', dir=output.parent) as temporary:
        staged = Path(temporary) / target.name
        with ZipFile(staged, 'w', ZIP_DEFLATED) as archive:
            for path in files + [checksum]:
                archive.write(path, 'bass-port/' + path.name)
        with ZipFile(staged) as archive:
            if archive.testzip() is not None:
                raise ValueError('Print ZIP failed readback')
        staged.replace(target)
    return target


if __name__ == '__main__':
    export()
