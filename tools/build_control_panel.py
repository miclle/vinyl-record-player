"""Independent control panel with four face mounting bores and a rear locating rim; drawing Y runs down from the front top-left."""
import hashlib
import html
import json
import math
import re
from zipfile import ZipFile, ZIP_DEFLATED
from pathlib import Path

import FreeCAD as App
import Mesh
import MeshPart
import Part

ROOT = Path(__file__).resolve().parents[1]
PARAMETERS = ROOT / 'cad/control-panel.json'
APPEARANCE = ROOT / 'cad/control-panel-appearance.json'
OUTPUT = ROOT / 'output/3d-print/control-panel'
STEM = 'Control-panel'
V = App.Vector


def load_parameters():
    return json.loads(PARAMETERS.read_text())


def load_appearance():
    appearance = json.loads(APPEARANCE.read_text())
    for key in ('panel_color','markings_color'):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',appearance[key]):
            raise ValueError(f'{key} must use #RRGGBB')
    return appearance


def logo_face(p):
    """Same continuous Sigmar One outline as Ariel-stencil; A/R counters remain open."""
    spec = p['front_logo']
    width, depth = spec['width_mm'], spec['depth_mm']
    if not (math.isfinite(width) and width > 0 and math.isfinite(depth)
            and 0 < depth < p['thickness_mm']):
        raise ValueError('Logo width and engraving depth must fit the plate')
    font = ROOT / spec['font']
    if not font.is_file():
        raise FileNotFoundError(font)
    letters = Part.makeWireString(spec['text'], str(font), 16, 0)
    flat = Part.makeCompound([Part.makeFace(wires, 'Part::FaceMakerBullseye')
                              for wires in letters])
    if len(flat.Faces) != 5 or not flat.isValid():
        raise ValueError('Ariel logo must form five valid letter faces')
    flat.scale(width / flat.optimalBoundingBox(False).XLength)
    b = flat.optimalBoundingBox(False)
    flat.translate(V(spec['center_x_mm'] - (b.XMin+b.XMax)/2,
                     p['height_mm']-spec['center_y_mm']-(b.YMin+b.YMax)/2, 0))
    b = flat.optimalBoundingBox(False)
    if min(b.XMin, b.YMin, p['width_mm']-b.XMax, p['height_mm']-b.YMax) < 2:
        raise ValueError('Logo must retain at least 2 mm edge clearance')
    for hole in p['holes']:
        disk = Part.Face(Part.Wire(Part.makeCircle(hole['diameter_mm']/2,
                         V(hole['x_mm'], p['height_mm']-hole['y_mm'], 0))))
        if flat.distToShape(disk)[0] < 2:
            raise ValueError('Logo must retain at least 2 mm bore clearance')
    return flat


def marking_faces(p):
    faces = list(logo_face(p).Faces)
    spec = p['front_markings']
    if spec['depth_mm'] != p['front_logo']['depth_mm']:
        raise ValueError('All front markings must share one inlay depth')
    font = str(ROOT / spec['font'])
    cap = Part.makeCompound(Part.makeWireString('M', font, 16, 0)[0]).BoundBox.YMax
    for label in spec['labels']:
        letters = Part.makeWireString(label['text'], font, 16, 0)
        flat = Part.makeCompound([Part.makeFace(wires, 'Part::FaceMakerBullseye') for wires in letters])
        flat.scale(label['cap_height_mm']/cap)
        b = flat.optimalBoundingBox(False)
        x = label['x_mm'] - (b.XMin+b.XMax)/2 if label['align']=='center' else label['x_mm']-b.XMin
        flat.translate(V(x, p['height_mm']-label['baseline_y_mm'], 0))
        faces.extend(flat.Faces)
    d = spec['divider']
    line = Part.makePlane(d['length_mm'], d['width_mm'],
                         V(d['x_mm'], p['height_mm']-d['y_mm']-d['width_mm']/2, 0))
    faces.append(line)
    flat = Part.makeCompound(faces)
    bounds = [face.optimalBoundingBox(False) for face in faces]
    for index, face in enumerate(faces):
        b = bounds[index]
        if min(b.XMin,b.YMin,p['width_mm']-b.XMax,p['height_mm']-b.YMax) < 0.5:
            raise ValueError('Marking reaches panel edge')
        for other, other_bounds in zip(faces[:index], bounds[:index]):
            if (b.XMax+0.05 < other_bounds.XMin or other_bounds.XMax+0.05 < b.XMin
                    or b.YMax+0.05 < other_bounds.YMin or other_bounds.YMax+0.05 < b.YMin):
                continue
            if face.distToShape(other)[0] < 0.05:
                raise ValueError(f'Front markings overlap or lack separation: face {index}, {b}, other {other.optimalBoundingBox(False)}')
        for hole in p['holes']:
            x, y, radius = hole['x_mm'], p['height_mm']-hole['y_mm'], hole['diameter_mm']/2
            if (x+radius+0.3 < b.XMin or x-radius-0.3 > b.XMax
                    or y+radius+0.3 < b.YMin or y-radius-0.3 > b.YMax):
                continue
            disk = Part.Face(Part.Wire(Part.makeCircle(hole['diameter_mm']/2,
                             V(hole['x_mm'],p['height_mm']-hole['y_mm'],0))))
            if face.distToShape(disk)[0] < 0.3:
                raise ValueError('Front marking reaches a bore')
    return flat


def marking_insert(p):
    # Consistent 0.002 mm polygon outlines keep thin glyph extrusions and saved STEP robust.
    return marking_mesh_proxy(p)


def marking_svg(p, color):
    import Draft
    temporary = App.newDocument('PanelMarkingArtwork', hidden=True, temp=True)
    try:
        obj = temporary.addObject('Part::Feature', 'MarkingPaths')
        obj.Shape = marking_polygon_faces(p)
        paths = Draft.getSVG(obj)
        paths = re.sub(r' stroke="[^"]*"| stroke-width="[^"]*"| style="[^"]*"| fill="[^"]*"', '', paths)
        paths = re.sub(r' id="[^"]*"', '', paths)
        return (f'<g data-front-markings="printable" fill="{color}" fill-rule="evenodd" '
                f'transform="translate(0 {p["height_mm"]}) scale(1 -1)">{paths}</g>')
    finally:
        App.closeDocument(temporary.Name)


def print_shape(shape, p):
    result = shape.copy()
    result.rotate(V(0,0,0),V(1,0,0),180)
    result.translate(V(0,p['height_mm'],p['thickness_mm']))
    return result


def marking_polygon_faces(p):
    """Shared polygon boundaries avoid inconsistent top/side curve tessellation."""
    faces = []
    for face in marking_faces(p).Faces:
        wires = []
        for wire in face.Wires:
            points = []
            for point in wire.discretize(Deflection=0.002):
                if not points or (point-points[-1]).Length > 1e-7:
                    points.append(point)
            if (points[-1]-points[0]).Length > 1e-7:
                points.append(points[0])
            wires.append(Part.Wire(Part.makePolygon(points).Edges))
        faces.append(Part.makeFace(wires,'Part::FaceMakerBullseye'))
    return Part.makeCompound(faces)


def marking_mesh_proxy(p):
    flat = marking_polygon_faces(p)
    flat.translate(V(0,0,p['thickness_mm']-p['front_markings']['depth_mm']))
    return flat.extrude(V(0,0,p['front_markings']['depth_mm']))


def mesh_volume(mesh):
    # FreeCAD Mesh.Volume accumulates in float precision, unsuitable for a wide thin plate.
    vertices, facets = mesh.Topology
    origin = mesh.BoundBox.Center
    terms = []
    for a,b,c in facets:
        u,v,w = (vertices[i]-origin for i in (a,b,c))
        terms.append(u.dot(v.cross(w))/6)
    return math.fsum(terms)


def write_color_3mf(path, meshes, appearance):
    # Keep parts unpainted; Bambu's per-part extruder metadata permits reassignment.
    ns = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
    model = [f'<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" xml:lang="en-US" xmlns="{ns}"><resources>',
             '<basematerials id="1">',
             f'<base name="Panel" displaycolor="{appearance["panel_color"]}FF"/>',
             f'<base name="Letters and Ariel" displaycolor="{appearance["markings_color"]}FF"/></basematerials>']
    for index, mesh in enumerate(meshes):
        vertices, triangles = mesh.Topology
        model.append(f'<object id="{index+2}" type="model" name="{("Panel","Letters and Ariel")[index]}"><mesh><vertices>')
        model.extend(f'<vertex x="{v.x:.9f}" y="{v.y:.9f}" z="{v.z:.9f}"/>' for v in vertices)
        model.append('</vertices><triangles>')
        model.extend(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a,b,c in triangles)
        model.append('</triangles></mesh></object>')
    model.append('<object id="4" type="model" name="Control panel"><components><component objectid="2"/><component objectid="3"/></components></object></resources><build><item objectid="4"/></build></model>')
    parts = ''.join(f'<part id="{i+2}" subtype="normal_part"><metadata key="name" value="{name}"/><metadata key="extruder" value="{i+1}"/></part>'
                    for i, name in enumerate(('Panel', 'Letters and Ariel')))
    model_settings = f'<?xml version="1.0" encoding="UTF-8"?><config><object id="4"><metadata key="name" value="Control panel"/><metadata key="extruder" value="1"/>{parts}</object></config>'
    with ZipFile(path,'w',ZIP_DEFLATED) as archive:
        archive.writestr('3D/3dmodel.model',''.join(model))
        archive.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        archive.writestr('_rels/.rels','<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        archive.writestr('Metadata/model_settings.config', model_settings)
        archive.writestr('Metadata/project_settings.config', json.dumps({
            'filament_colour': [appearance['panel_color'], appearance['markings_color']],
            'filament_type': ['PLA', 'PLA'], 'filament_diameter': ['1.75', '1.75']}))


def rim_shape(p):
    """Rear locating rim below Z=0; the front plate surface is Z=thickness."""
    rim, window = p['back_rim'], p['mounting']['wood_window']
    clearance, wall, height = (rim[key] for key in
                               ('window_clearance_per_side_mm', 'wall_thickness_mm', 'height_mm'))
    if any(not math.isfinite(v) or v <= 0 for v in (clearance, wall, height)):
        raise ValueError('Rim dimensions must be finite and positive')
    x, y = window['x_mm'] + clearance, window['y_mm'] + clearance
    width, length = window['width_mm'] - 2*clearance, window['height_mm'] - 2*clearance
    if min(width, length) <= 2*wall or min(x, y, p['width_mm']-x-width, p['height_mm']-y-length) <= 0:
        raise ValueError('Rim must fit inside the panel and retain an inner opening')
    bottom = p['height_mm'] - y - length
    z = -height
    if rim['edges'] != ['left', 'right']:
        raise ValueError('This panel uses only left and right rear locating ribs')
    frame = Part.makeCompound([Part.makeBox(wall, length, height, V(left, bottom, z))
                               for left in (x, x+width-wall)])
    if not frame.isValid() or len(frame.Solids) != 2:
        raise ValueError('Rear locating ribs must form two separate solids before joining the plate')
    for hole in p['holes']:
        probe = Part.makeCylinder(hole['diameter_mm']/2, height,
                                  V(hole['x_mm'], p['height_mm']-hole['y_mm'], z))
        if frame.common(probe).Volume > 1e-7:
            raise ValueError('Rim obstructs a panel bore')
    return frame


def build(p, insert=None):
    width, height, thickness = (p[key] for key in ('width_mm', 'height_mm', 'thickness_mm'))
    if any(not math.isfinite(value) or value <= 0 for value in (width, height, thickness)):
        raise ValueError('Panel dimensions must be finite and positive')
    holes = p['holes']
    if not holes or len({hole['id'] for hole in holes}) != len(holes):
        raise ValueError('Use nonempty holes with unique IDs')
    for index, hole in enumerate(holes):
        x, y, diameter = (hole[key] for key in ('x_mm', 'y_mm', 'diameter_mm'))
        if any(not math.isfinite(value) for value in (x, y, diameter)) or diameter <= 0:
            raise ValueError('Hole coordinates and diameters must be finite; diameter positive')
        radius = diameter / 2
        if min(x, width - x, y, height - y) <= radius:
            raise ValueError(f'{hole["id"]} reaches a panel edge')
        for other in holes[:index]:
            distance = math.hypot(x - other['x_mm'], y - other['y_mm'])
            if distance <= radius + other['diameter_mm'] / 2:
                raise ValueError('Hole boundaries must remain separate')
    shape = Part.makeBox(width, height, thickness)
    for hole in holes:
        # Front drawing X=x, Y=height-y. CAD plate is Z=0..thickness; rear rim below Z=0.
        bore = Part.makeCylinder(hole['diameter_mm'] / 2, thickness + 2,
                                 V(hole['x_mm'], height - hole['y_mm'], -1))
        shape = shape.cut(bore)
    shape = shape.fuse(rim_shape(p)).removeSplitter()
    insert = marking_insert(p) if insert is None else insert
    shape = shape.cut(insert).removeSplitter()
    if not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError('Panel must be one valid solid')
    return shape


def assert_same_geometry(actual, expected):
    """Compare all saved planar glyph faces, curve edges and vertices without a huge coincident boolean."""
    def vertex_signature(shape):
        return sorted(tuple(round(value,5) for value in (v.Point.x,v.Point.y,v.Point.z))
                      for v in shape.Vertexes)
    def edge_signature(shape):
        return sorted((type(e.Curve).__name__,round(e.Length,5)) for e in shape.Edges)
    def face_signature(shape):
        return sorted((type(f.Surface).__name__,round(f.Area,4),
                       tuple(round(value,4) for value in f.CenterOfMass),len(f.Wires))
                      for f in shape.Faces)
    if (len(actual.Solids)!=len(expected.Solids)
            or vertex_signature(actual)!=vertex_signature(expected)
            or edge_signature(actual)!=edge_signature(expected)
            or face_signature(actual)!=face_signature(expected)):
        raise ValueError('Saved face, edge or vertex geometry differs')


def verify_exports(output, expected, p):
    """Read saved solids and actual cylindrical bores, then check STL topology."""
    doc = App.openDocument(str(output / f'{STEM}.FCStd'))
    try:
        step = Part.Shape()
        step.read(str(output / f'{STEM}.step'))
        if json.loads(doc.ControlPanel.DesignJSON) != p:
            raise ValueError("Saved design snapshot differs")
        step_base = max(step.Solids, key=lambda solid: solid.Volume)
        step_markings = Part.makeCompound([solid for solid in step.Solids if solid.Volume < step_base.Volume/2])
        insert = marking_insert(p)
        assert_same_geometry(step_markings,insert)
        assert_same_geometry(doc.Markings.Shape,insert)
        shapes = (doc.ControlPanel.Shape, step_base)
        analytic_volume = p['width_mm'] * p['height_mm'] * p['thickness_mm']
        analytic_volume -= sum(math.pi * (h['diameter_mm'] / 2) ** 2
                               * p['thickness_mm'] for h in p['holes'])
        rim, window = p['back_rim'], p['mounting']['wood_window']
        frame_length = window['height_mm'] - 2*rim['window_clearance_per_side_mm']
        wall = rim['wall_thickness_mm']
        analytic_volume += 2*wall*frame_length*rim['height_mm']
        analytic_volume -= marking_insert(p).Volume
        for shape in shapes:
            if not shape.isValid() or len(shape.Solids) != 1:
                raise ValueError('Invalid saved panel solid')
            bounds = shape.optimalBoundingBox(False)
            values = (bounds.XMin, bounds.YMin, bounds.ZMin, bounds.XLength,
                      bounds.YLength, bounds.ZLength)
            targets = (0, 0, -p['back_rim']['height_mm'], p['width_mm'], p['height_mm'], p['thickness_mm'] + p['back_rim']['height_mm'])
            if any(abs(a - b) > 1e-6 for a, b in zip(values, targets)):
                raise ValueError('Saved panel envelope differs')
            cylinders = [face for face in shape.Faces if isinstance(face.Surface, Part.Cylinder)]
            if len(cylinders) != len(p['holes']):
                raise ValueError('Saved hole count differs')
            for hole in p['holes']:
                center = V(hole['x_mm'], p['height_mm'] - hole['y_mm'], 0)
                matching = [face for face in cylinders
                            if abs(face.Surface.Radius - hole['diameter_mm'] / 2) < 1e-6
                            and math.hypot(face.Surface.Center.x - center.x,
                                           face.Surface.Center.y - center.y) < 1e-6
                            and abs(abs(face.Surface.Axis.z) - 1) < 1e-6]
                if len(matching) != 1:
                    raise ValueError(f'Saved bore differs: {hole["id"]}')
                bore_bounds = matching[0].optimalBoundingBox(False)
                if abs(bore_bounds.ZMin) > 1e-6 or abs(bore_bounds.ZMax - p['thickness_mm']) > 1e-6:
                    raise ValueError('Saved bore must run through the whole panel')
            if abs(shape.Volume - analytic_volume) > 1e-4:
                raise ValueError('Saved panel volume differs from plate, rim and engraving volume')
            assert_same_geometry(shape,expected)
        mesh = Mesh.Mesh(str(output / f'{STEM}.stl'))
        if (not mesh.isSolid() or mesh.countComponents() != 1 or mesh.Volume <= 0
                or mesh.hasNonManifolds() or mesh.hasSelfIntersections()):
            raise ValueError('STL must be one closed, manifold, positive-volume component')
        bounds = mesh.BoundBox
        values = (bounds.XMin, bounds.YMin, bounds.ZMin, bounds.XLength, bounds.YLength, bounds.ZLength)
        targets = (0, 0, 0, p['width_mm'], p['height_mm'], p['thickness_mm']+p['back_rim']['height_mm'])
        if any(abs(a-b)>1e-5 for a,b in zip(values, targets)):
            raise ValueError('STL print envelope differs')
        if abs(mesh_volume(mesh) - expected.Volume) > 0.7:
            raise ValueError('STL volume differs excessively from CAD')
        ink_mesh = Mesh.Mesh(str(output / f'{STEM}-markings.stl'))
        if not ink_mesh.isSolid() or ink_mesh.hasNonManifolds() or ink_mesh.hasSelfIntersections():
            raise ValueError('Invalid lettering mesh')
        if ink_mesh.countComponents() != len(insert.Solids) or abs(mesh_volume(ink_mesh)-insert.Volume) > 0.1:
            raise ValueError('Lettering mesh differs from CAD')
        return dict(passed=True, valid_solid=True, solid_count=1,
                    hole_count=len(p['holes']), functional_hole_count=7, mounting_hole_count=4,
                    cad_total_solid_count=1+len(insert.Solids),
                    rear_rim_height_mm=p['back_rim']['height_mm'],
                    rear_rim_edges=p['back_rim']['edges'],
                    total_print_thickness_mm=p['thickness_mm']+p['back_rim']['height_mm'],
                    saved_hole_positions_and_diameters_match=True,
                    through_holes=True, cad_step_readback_match=True,
                    saved_geometry_check="All face areas and centroids, edge types and lengths, vertex positions, volumes and bore surfaces",
                    printable_markings=True, marking_solid_count=len(insert.Solids),
                    markings_mesh_closed=True, markings_mesh_components=ink_mesh.countComponents(),
                    front_logo_engraved=True, logo_depth_mm=p['front_logo']['depth_mm'],
                    logo_floor_thickness_mm=p['thickness_mm']-p['front_logo']['depth_mm'],
                    volume_mm3=expected.Volume, closed_mesh=True, mesh_components=1,
                    mesh_nonmanifold_edges=False, mesh_self_intersections=False,
                    triangles=mesh.CountFacets, mesh_volume_mm3=mesh_volume(mesh), markings_mesh_volume_mm3=mesh_volume(ink_mesh),
                    mesh_outline_deflection_mm=0.002)
    finally:
        App.closeDocument(doc.Name)


def outline_svg(p):
    """1:1 front outline without kerf compensation or lettering cuts."""
    width, height = p['width_mm'], p['height_mm']
    holes = ''.join(f'<circle cx="{h["x_mm"]:g}" cy="{h["y_mm"]:g}" '
                    f'r="{h["diameter_mm"] / 2:g}"/>' for h in p['holes'])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}mm" '
            f'height="{height:g}mm" viewBox="0 0 {width:g} {height:g}">\n'
            f'<g fill="none" stroke="black" stroke-width="0.1">'
            f'<rect width="{width:g}" height="{height:g}"/>{holes}</g>\n</svg>\n')


def face_svg(p, appearance):
    width, height = p['width_mm'], p['height_mm']
    shift = appearance['label_shift_x_mm']
    holes = p['holes']
    radius = appearance['knob_cap_diameter_mm']/2
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError('Knob cap diameter must be finite and positive')
    for hole in holes:
        if hole['id'].endswith('Knob') and min(hole['x_mm'], width-hole['x_mm'], hole['y_mm'], height-hole['y_mm']) <= radius:
            raise ValueError('Knob cap projection reaches a panel edge')
    circles = ''.join(f'<circle cx="{h["x_mm"]}" cy="{h["y_mm"]}" r="{h["diameter_mm"]/2}" fill="#eff3f7"/>' for h in holes)
    caps = ''.join(f'<g data-knob-cap="{h["id"]}"><circle cx="{h["x_mm"]}" cy="{h["y_mm"]}" r="{radius:g}" fill="#bfc0c0"/><path d="M {h["x_mm"]} {h["y_mm"]-radius+1} v 1.5" stroke="#4f5d75" stroke-width="0.3"/></g>' for h in holes if h['id'].endswith('Knob'))
    heads = ''.join(f'<circle cx="{h["x_mm"]}" cy="{h["y_mm"]}" r="{p["mounting"]["screw_head_diameter_mm"]/2}" fill="#bfc0c0"/><path d="M {h["x_mm"]-1.25} {h["y_mm"]} h 2.5 M {h["x_mm"]} {h["y_mm"]-1.25} v 2.5" stroke="#4f5d75" stroke-width="0.3"/>' for h in holes if h['role']=='mounting')
    return (f'<rect width="{width:g}" height="{height:g}" fill="{appearance["panel_color"]}"/>'
            f'{circles}{caps}{heads}{marking_svg(p,appearance["markings_color"])}')


def preview_svg(p, appearance=None):
    appearance = appearance or load_appearance()
    width, height = p['width_mm'], p['height_mm']
    holes = p['holes']
    face = face_svg(p, appearance)
    bores = ''.join(f'<circle cx="{h["x_mm"]}" cy="{h["y_mm"]}" r="{h["diameter_mm"]/2}"/>' for h in p['holes'])
    rows = ''.join(f'<text x="780" y="{240+i*38}">{html.escape(h["label"])}</text><text x="980" y="{240+i*38}">{h["x_mm"]:g}</text><text x="1050" y="{240+i*38}">{h["y_mm"]:g}</text><text x="1120" y="{240+i*38}">{h["diameter_mm"]:g}</text>' for i,h in enumerate(p['holes']))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="960" viewBox="0 0 1240 960">
<rect width="1240" height="960" fill="#f5f7fa"/><g font-family="PingFang SC, sans-serif" fill="#223348">
<text x="52" y="57" font-size="30" font-weight="600">唱机 + 音响 · 四螺丝面板与背面两侧定位条</text>
<text x="52" y="97" font-size="19">{width:g} × {height:g} mm｜正面厚 3.5，背框高 10，总厚 13.5 mm｜7 个功能孔 + 4 个固定孔</text>
<text x="52" y="153" font-size="20" font-weight="600">正面标识 · Ø14 金属帽 / Ø7 螺丝头</text>
<text x="432" y="153" font-size="20" font-weight="600">开孔定位图</text><text x="780" y="153" font-size="20" font-weight="600">孔位表 · 左上角原点 / mm</text>
<g transform="translate(52 200) scale(3.45)">{face}</g>
<g transform="translate(440 220) scale(3.3)" stroke="#42556b" stroke-width="0.2" fill="none"><rect width="{width:g}" height="{height:g}" fill="white"/>{bores}<path d="M {next(h["x_mm"] for h in holes if h["id"]=="VolumeKnob"):g} 0 V {height:g}" stroke="#8ea8bd" stroke-dasharray="1.5 1"/>
<g font-size="3" fill="#42556b" stroke="none"><text x="{width/2:g}" y="-7" text-anchor="middle">{width:g}</text><text x="-6" y="{height/2:g}" text-anchor="end">{height:g}</text></g></g>
<g font-size="16" fill="#687a8e"><text x="780" y="195">功能</text><text x="980" y="195">X</text><text x="1050" y="195">Y</text><text x="1120" y="195">Ø</text></g><g font-size="17">{rows}</g>
<g font-size="17" fill="#516479"><text x="780" y="696">两侧定位条：各 1.5 × 135.4 × 10 mm。</text><text x="780" y="730">上下开放，面板底边 Y=160。</text><text x="780" y="764">木板窗口试排：{p["mounting"]["wood_window"]["width_mm"]:g} × {p["mounting"]["wood_window"]["height_mm"]:g} mm。</text><text x="780" y="798">PCB 下缘 Y=157；木条配合需核对。</text></g>
<text x="52" y="865" font-size="17">文字和 Ariel LOGO 均为 0.5 mm 分色嵌字，可打印；黑色面板，白色标识。</text>
<text x="52" y="907" font-size="17" fill="#687a8e">CAD：X=x，Y={height:g}−y，背框 Z=−10…0；STL 正面朝下，外廓 {width:g} × {height:g} × 13.5。</text>
</g></svg>\n'''


def render_model_preview(view, p, path, rear=False):
    """Use an explicit camera to avoid animated view transitions in exports."""
    center = V(p['width_mm'] / 2, p['height_mm'] / 2, 0)
    direction = V(1, -1, -1) if rear else V(0, 0, 1)
    direction.normalize()
    distance = 2 * max(p['width_mm'], p['height_mm'])
    position = center + direction * distance
    rotation = App.Rotation(V(0, 0, 1), direction)
    axis = rotation.Axis
    view.setCamera(f'''#Inventor V2.1 ascii
OrthographicCamera {{
  viewportMapping ADJUST_CAMERA
  position {position.x} {position.y} {position.z}
  orientation {axis.x} {axis.y} {axis.z} {rotation.Angle}
  nearDistance 1
  farDistance {10 * max(p['width_mm'], p['height_mm'])}
  aspectRatio 1
  focalDistance {distance}
  height {1.2 * p['height_mm']}
}}
''')
    view.saveImage(str(path), 1000, 1200, 'White')


def export(output=OUTPUT, prepared_shapes=None):
    if not App.GuiUp:
        raise RuntimeError('Use build-control-panel.FCMacro in the FreeCAD GUI')
    import FreeCADGui as Gui

    output = Path(output)
    target = (output / f'{STEM}.FCStd').resolve()
    if any(doc.FileName and Path(doc.FileName).resolve() == target
           for doc in App.listDocuments().values()):
        raise RuntimeError('Close Control-panel.FCStd before regenerating; save edits separately')
    p = load_parameters()
    shape = prepared_shapes[0] if prepared_shapes else build(p)
    output.mkdir(parents=True, exist_ok=True)
    doc = App.newDocument('ControlPanelPrint')
    try:
        obj = doc.addObject('Part::Feature', 'ControlPanel')
        obj.Label = f'唱机 + 音响旋钮面板 · {p["width_mm"]:g} × {p["height_mm"]:g} · 11 孔 · 背面定位框'
        obj.Shape = shape
        obj.addProperty('App::PropertyString', 'DesignJSON', 'Design').DesignJSON = json.dumps(p, ensure_ascii=False)
        obj.ViewObject.Visibility = True
        appearance = load_appearance()
        rgb = lambda color: tuple(int(color[i:i+2],16)/255 for i in (1,3,5))
        obj.ViewObject.ShapeColor = rgb(appearance['panel_color'])
        markings = doc.addObject('Part::Feature','Markings')
        markings.Label = '白色功能文字 + Ariel LOGO · 齐平嵌字'
        markings.Shape = prepared_shapes[1] if prepared_shapes else marking_insert(p)
        markings.ViewObject.ShapeColor = rgb(appearance['markings_color'])
        markings.ViewObject.DisplayMode = 'Shaded'
        markings.ViewObject.Visibility = True
        obj.ViewObject.LineColor = (0.05, 0.07, 0.09)
        obj.ViewObject.DisplayMode = 'Flat Lines'
        doc.recompute()
        mesh_shapes = (shape,markings.Shape)
        meshes = [MeshPart.meshFromShape(Shape=print_shape(s,p), LinearDeflection=0.005,
                                         AngularDeflection=0.06,Relative=False)
                  for s in mesh_shapes]
        mesh = meshes[0]
        mesh.write(str(output / f'{STEM}.stl'))
        meshes[1].write(str(output / f'{STEM}-markings.stl'))
        write_color_3mf(output / f'{STEM}-color.3mf',meshes,appearance)
        step = output / f'{STEM}.step'
        Part.export([obj,markings], str(step))
        step.write_text('\n'.join(line.rstrip() for line in step.read_text().splitlines()) + '\n')
        view = Gui.getDocument(doc.Name).activeView()
        view.viewAxonometric()
        view.fitAll()
        Gui.updateGui()
        doc.saveAs(str(target))
        render_model_preview(view, p, ROOT / 'previews/control-panel-front-model.png')
        render_model_preview(view, p, ROOT / 'previews/control-panel-model.png', rear=True)
    finally:
        App.closeDocument(doc.Name)
    report = dict(parameters=p, cad_coordinates='X=x; Y=height-y; front face Z=3.5; plate Z=0..3.5; rear rim Z=-10..0',
                  stl_print_coordinates=f'Rotate CAD 180 degrees about X, translate Y by {p["height_mm"]:g} and Z by 3.5: X=x, Y=y, front face Z=0, rear rim Z=3.5..13.5',
                  appearance=load_appearance(),
                  validation=verify_exports(output, shape, p))
    filenames = [f'{STEM}.{suffix}' for suffix in ('FCStd','step','stl')]
    filenames += [f'{STEM}-markings.stl',f'{STEM}-color.3mf']
    report['sha256'] = {name: hashlib.sha256((output/name).read_bytes()).hexdigest()
                        for name in filenames}
    report['verification_sources_sha256'] = {path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
        for path in ('tools/build_control_panel.py','tests/test_control_panel.py',
                     'cad/control-panel.json','cad/control-panel-appearance.json',
                     p['front_logo']['font'], p['front_markings']['font'])}
    report['color_parts'] = dict(panel=appearance['panel_color'], markings=appearance['markings_color'],
                                inlay_depth_mm=0.5, same_origin=True, printer_profile_included=False)
    (output / f'{STEM}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (output / f'{STEM}-outline.svg').write_text(outline_svg(p))
    (ROOT / 'previews/control-panel.svg').write_text(preview_svg(p))
    print(json.dumps(report['validation'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    export()
