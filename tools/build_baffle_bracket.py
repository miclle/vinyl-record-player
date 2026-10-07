"""Independent gusseted screw-mounted brace fitted to the saved baffle/bottom joint."""
import hashlib
import json
import math
from pathlib import Path
import tempfile

import FreeCAD as App
import Mesh
import MeshPart
import Part

from assembly_pose import set_cover_angle

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/3d-print/baffle-bracket'
LENGTH = 50.0  # Along the cabinet bottom, front to rear.
WIDTH = 50.0  # Across the cabinet.
HEIGHT = 50.0  # Vertical installed height.
THICKNESS = 6.0  # True normal wall thickness, including both side gussets.
HOLE_DIAMETER = 4.0
CHAMFER = 0.3
HOLE_X = (12.5, 37.5)
HOLE_DISTANCE = 30.0  # Along each mounting face from the front/bottom joint.
CENTERS_X = (170.0, 280.0)
V = App.Vector


def build(p):
    """Print coordinates follow assembly axes; the bottom mounting face is on bed."""
    angle = p['front_angle']
    if not 0 < angle < 90:
        raise ValueError('Expected a rearward-leaning baffle between 0 and 90 degrees')
    radians = math.radians(angle)
    sine, cosine = math.sin(radians), math.cos(radians)
    rake = HEIGHT / math.tan(radians)
    normal_offset = THICKNESS / sine
    if rake + normal_offset >= LENGTH:
        raise ValueError('Baffle slope leaves no usable bracket at the requested height')

    def prism(profile, x, width):
        points = [V(x, y, z) for y, z in profile]
        return Part.Face(Part.makePolygon(points + [points[0]])).extrude(V(width, 0, 0))

    # Two mounting leaves, true normal thickness 6 mm; two full side gussets.
    leaves = [(0, 0), (LENGTH, 0), (LENGTH, THICKNESS),
              (THICKNESS / math.tan(radians) + normal_offset, THICKNESS),
              (rake + normal_offset, HEIGHT), (rake, HEIGHT)]
    triangle = [(0, 0), (LENGTH, 0), (rake, HEIGHT)]
    shape = prism(leaves, 0, WIDTH).multiFuse([
        prism(triangle, 0, THICKNESS),
        prism(triangle, WIDTH - THICKNESS, THICKNESS)]).removeSplitter()
    holes = []
    for face, direction in [('Bottom', V(0, 0, 1)),
                            ('Baffle', V(0, sine, -cosine))]:
        for x in HOLE_X:
            center = (V(x, HOLE_DISTANCE, 0) if face == 'Bottom' else
                      V(x, HOLE_DISTANCE * cosine, HOLE_DISTANCE * sine))
            bore = Part.makeCylinder(HOLE_DIAMETER / 2, THICKNESS + 0.2,
                                     center - direction * 0.1, direction)
            # Small lead-in on both mouths; not a recessed screw-head seat.
            entry = Part.makeCone(HOLE_DIAMETER / 2 + CHAMFER,
                                  HOLE_DIAMETER / 2, CHAMFER, center, direction)
            exit_point = center + direction * THICKNESS
            exit_chamfer = Part.makeCone(HOLE_DIAMETER / 2 + CHAMFER,
                                         HOLE_DIAMETER / 2, CHAMFER,
                                         exit_point, -direction)
            shape = shape.cut(bore).cut(entry).cut(exit_chamfer)
            holes.append(dict(face=face, center_mm=[center.x, center.y, center.z],
                              inward_axis=[direction.x, direction.y, direction.z]))
    shape = shape.removeSplitter()
    if not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError('Bracket must be one valid solid')
    bottom_z = p['foot_height'] + p['wall']
    baffle_rear_y = 16 + p['acoustic']['baffle_thickness'] / sine
    openings_area = len(HOLE_X) * math.pi * (HOLE_DIAMETER / 2 + CHAMFER) ** 2
    metadata = dict(
        design='Open screw-mounted angle bracket with two triangular side gussets',
        units='mm', length_mm=LENGTH, width_mm=WIDTH, vertical_height_mm=HEIGHT,
        wall_thickness_mm=THICKNESS, print_size_mm=[WIDTH, LENGTH, HEIGHT],
        joint_angle_deg=angle, top_setback_mm=rake,
        sloping_contact_length_mm=HEIGHT / sine,
        bottom_contact_area_mm2=LENGTH * WIDTH - openings_area,
        baffle_contact_area_mm2=HEIGHT / sine * WIDTH - openings_area,
        hole_diameter_mm=HOLE_DIAMETER, holes_per_face=2, hole_count=len(holes),
        transverse_hole_pitch_mm=HOLE_X[1] - HOLE_X[0],
        hole_distance_from_joint_mm=HOLE_DISTANCE,
        chamfer_mm=CHAMFER, chamfer_angle_deg=45, chamfer_mouth_diameter_mm=HOLE_DIAMETER + 2 * CHAMFER,
        chamfer_scope='Both mouths of each hole; not a screw-head countersink',
        holes=holes, volume_mm3=shape.Volume,
        print_orientation='Bottom mounting face on bed; Z=0..50 mm; inspect angled holes in slicer',
        mounting='Four diameter-4 mm through holes; screw type, head and engagement unconfirmed',
        installation_centers_x_mm=list(CENTERS_X),
        installation_root_yz_mm=[baffle_rear_y, bottom_z],
        installation_released=False,
    )
    return shape, metadata


def installed_shape(printable, metadata, center_x):
    """Translate the bottom-on-bed model into the cabinet without changing axes."""
    shape = printable.copy()
    y, z = metadata['installation_root_yz_mm']
    shape.translate(V(center_x - WIDTH / 2, y, z))
    return shape


def check_fit(printable, metadata, p, source=None):
    """Read a private copy and check each solid, including compound members."""
    source = Path(source or ROOT / 'cad/record-player.FCStd')
    results = []
    with tempfile.TemporaryDirectory() as temporary:
        copied = Path(temporary) / 'BaffleBracketFit.FCStd'
        copied.write_bytes(source.read_bytes())
        doc = App.openDocument(str(copied))
        try:
            snapshot = json.dumps(p, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            if doc.GeometryDatums.BuildParametersJSON != snapshot:
                raise ValueError('Saved assembly parameters differ; rebuild before fitting the bracket')
            set_cover_angle(doc, p, 0)
            objects = [obj for obj in doc.Objects if obj.TypeId == 'Part::Feature'
                       and not getattr(obj, 'IsReference', False)
                       and not getattr(obj, 'IsDiagnostic', False)]
            for x in metadata['installation_centers_x_mm']:
                bracket = installed_shape(printable, metadata, x)
                contacts = {}
                for obj in objects:
                    # Compound.common can miss full containment; check each solid.
                    overlap = sum(bracket.common(solid).Volume for solid in obj.Shape.Solids)
                    if overlap > 1e-6:
                        raise ValueError(f'Bracket at X={x:g} overlaps {obj.Name}: {overlap:g} mm3')
                    if obj.Name in ('Baffle', 'Bottom'):
                        # Solid intersection intentionally omits zero-volume faces.
                        contacts[obj.Name] = sum(face.common(obj.Shape).Area for face in bracket.Faces)
                for name, expected in [('Bottom', metadata['bottom_contact_area_mm2']),
                                       ('Baffle', metadata['baffle_contact_area_mm2'])]:
                    if abs(contacts.get(name, 0) - expected) > 1e-5:
                        raise ValueError(f'Incomplete {name} contact at X={x:g}')
                results.append(dict(center_x_mm=x, checked_physical_objects=len(objects),
                                    overlap_mm3=0, contact_area_mm2=contacts))
        finally:
            App.closeDocument(doc.Name)
    return dict(model_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), positions=results)


def verify_exports(output, expected):
    """Read back CAD, STEP and STL against the generated print solid."""
    output = Path(output)
    doc = App.openDocument(str(output / 'Baffle-bracket.FCStd'))
    try:
        step = Part.Shape()
        step.read(str(output / 'Baffle-bracket.step'))
        for shape in (doc.BaffleBracket.Shape, step):
            if not shape.isValid() or len(shape.Solids) != 1:
                raise ValueError('Invalid saved bracket solid')
            if max(shape.cut(expected).Volume, expected.cut(shape).Volume) > 1e-6:
                raise ValueError('Saved export differs from the generated bracket')
        mesh = Mesh.Mesh(str(output / 'Baffle-bracket.stl'))
        if not mesh.isSolid() or mesh.countComponents() != 1 or mesh.Volume <= 0:
            raise ValueError('STL must be one closed, positive-volume component')
        if abs(mesh.Volume - expected.Volume) > 0.5:
            raise ValueError('STL volume differs from CAD')
        return dict(valid_solid=True, solid_count=1, cad_step_readback_match=True,
                    closed_mesh=True, mesh_components=1, triangles=mesh.CountFacets,
                    mesh_volume_mm3=mesh.Volume)
    finally:
        App.closeDocument(doc.Name)


def preview_svg(shape, data):
    """Dimensioned side section and actual solid projection from the open side."""
    import TechDraw

    projection = TechDraw.projectToSVG(shape, V(1, 2, 1.5))
    projection = projection.replace('transform="scale(1, -1)"', '').replace(
        'stroke-width="1.0"', 'stroke-width="0.18"')
    tip_x = 80 + 6 * data['top_setback_mm']
    inner_x = tip_x + 6 * THICKNESS / math.sin(math.radians(data['joint_angle_deg']))
    inner_root_x = 80 + 6 * (THICKNESS / math.tan(math.radians(data['joint_angle_deg']))
                           + THICKNESS / math.sin(math.radians(data['joint_angle_deg'])))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="700" viewBox="0 0 1200 700">
<rect width="1200" height="700" fill="#f4f5f7"/>
<g font-family="PingFang SC, sans-serif" fill="#1c2939">
<text x="50" y="50" font-size="28" font-weight="bold">倾斜障板角码 · 四孔与两侧加强筋</text>
<text x="50" y="85" font-size="18">长 × 宽 × 高：50 × 50 × 50 mm｜安装板及侧筋厚 6 mm｜贴合夹角 {data['joint_angle_deg']:g}°</text>
<text x="65" y="132" font-size="18">中间剖面（不含两侧三角加强筋）</text>
<text x="570" y="132" font-size="18">实际模型投影 · 中间敞开，供拧螺丝</text>
</g>
<path d="M 60 500 H 415 V 524 H 60 Z" fill="#c5b49a"/>
<path d="M 80 500 L {tip_x} 200 H {tip_x-24} L 56 500 Z" fill="#c5b49a"/>
<path d="M 80 500 H 380 V 464 H {inner_root_x} L {inner_x} 200 H {tip_x} Z" fill="#89b5d6" stroke="#254b67" stroke-width="2"/>
<g stroke="#64748b" stroke-width="1.5" fill="none">
<path d="M 80 535 V 565 M 380 535 V 565 M 80 552 H 380 M 75 557 L 85 547 M 375 557 L 385 547"/>
<path d="M 400 500 H 450 M {inner_x+8} 200 H 450 M 436 200 V 500 M 431 205 L 441 195 M 431 505 L 441 495"/>
</g>
<g font-family="PingFang SC, sans-serif" fill="#1c2939" font-size="18">
<text x="200" y="584">50 mm</text><text x="448" y="355">50 mm</text>
<text x="145" y="447">{data['joint_angle_deg']:g}°</text>
<text x="65" y="185">障板背面</text><text x="275" y="519" font-size="15">底板顶面</text>
<text x="580" y="540">两个安装面各 2 × Ø4 mm 通孔，共四孔。</text>
<text x="580" y="572">横向孔距 25 mm，距两侧各 12.5 mm。</text>
<text x="580" y="604">各孔两端 C0.3 × 45°，孔口 Ø4.6 mm。</text>
<text x="50" y="655" font-size="16">底面朝下打印；螺钉头型、实际孔径及旋拧工具需实物核对。主 CAD 未修改。</text>
</g>
<g transform="translate(680 430) scale(4.5 -4.5)">{projection}</g>
</svg>\n'''
    return '\n'.join(line.rstrip() for line in svg.splitlines()) + '\n'


def export(output=OUTPUT):
    """Export a visible GUI document without changing the main assembly."""
    if not App.GuiUp:
        raise RuntimeError('Export with tools/build-baffle-bracket.FCMacro in the FreeCAD GUI')
    import FreeCADGui as Gui

    output = Path(output)
    target = (output / 'Baffle-bracket.FCStd').resolve()
    if any(doc.FileName and Path(doc.FileName).resolve() == target
           for doc in App.listDocuments().values()):
        raise RuntimeError('Close Baffle-bracket.FCStd before regenerating; save edits separately')
    p = json.loads((ROOT / 'cad/parameters.json').read_text())
    shape, data = build(p)
    data['assembly_fit'] = check_fit(shape, data, p)
    output.mkdir(parents=True, exist_ok=True)
    doc = App.newDocument('BaffleBracketPrint')
    try:
        obj = doc.addObject('Part::Feature', 'BaffleBracket')
        obj.Label = '倾斜障板角码 · 50 × 50 × 50 mm · 壁厚 6 mm · 四孔（打印姿态）'
        obj.Shape = shape
        obj.addProperty('App::PropertyString', 'DesignJSON', 'Design').DesignJSON = json.dumps(data, ensure_ascii=False)
        obj.ViewObject.Visibility = True
        obj.ViewObject.ShapeColor = (0.54, 0.71, 0.84)
        obj.ViewObject.LineColor = (0.15, 0.25, 0.34)
        obj.ViewObject.DisplayMode = 'Flat Lines'
        doc.recompute()
        mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.01,
                                      AngularDeflection=0.08, Relative=False)
        mesh.write(str(output / 'Baffle-bracket.stl'))
        step_path = output / 'Baffle-bracket.step'
        Part.export([obj], str(step_path))
        step_path.write_text('\n'.join(line.rstrip() for line in step_path.read_text().splitlines()) + '\n')
        view = Gui.getDocument(doc.Name).activeView()
        view.setCameraOrientation(App.Rotation(V(1, 0, 0), V(0, 0, 1), V(0.4, 3, 2.5), 'ZYX').Q)
        view.fitAll()
        Gui.updateGui()
        view.saveImage(str(ROOT / 'previews/baffle-bracket-model.png'), 1600, 1200, 'White')
        doc.saveAs(str(target))
    finally:
        App.closeDocument(doc.Name)
    data['validation'] = verify_exports(output, shape)
    (output / 'Baffle-bracket.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    (ROOT / 'previews/baffle-bracket.svg').write_text(preview_svg(shape, data))
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    export()
