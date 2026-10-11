"""Independent, face-removable seven-slat positioning combs; GUI export only."""
import hashlib
import json
import math
from pathlib import Path

import FreeCAD as App
import Mesh
import MeshPart
import Part

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/3d-print/grille-jigs'
STEM = 'Grille-positioning-jigs'
V = App.Vector
COUNT = 7
FACE_WIDTH = 6.0
PROJECTION = 10.0
GAP = 6.0
PITCH = FACE_WIDTH + GAP
SLOT_WIDTH = 6.3
HEIGHT = 90.0
WIDTH = 22.0
BACK = 3.0
ENGAGEMENT = 7.0
MOUTH_CHAMFER = 0.4
SLOT_START = (HEIGHT - (COUNT * FACE_WIDTH + (COUNT - 1) * GAP)) / 2
BOTTOM_GAP = 6.0
BAFFLE_ANGLE = float(json.loads((ROOT / 'cad/parameters.json').read_text())['front_angle'])


def slot_bounds(index):
    low = SLOT_START + index * PITCH - (SLOT_WIDTH - FACE_WIDTH) / 2
    return low, low + SLOT_WIDTH


def build_comb():
    """Back on Z=0; teeth up. Wood enters from +Z without an undercut."""
    shape = Part.makeBox(WIDTH, HEIGHT, BACK + ENGAGEMENT)
    for i in range(COUNT):
        low, high = slot_bounds(i)
        top = BACK + ENGAGEMENT
        c = MOUTH_CHAMFER
        points = [V(-1, low, BACK), V(-1, high, BACK),
                  V(-1, high, top - c), V(-1, high + c, top),
                  V(-1, high + c, top + 1), V(-1, low - c, top + 1),
                  V(-1, low - c, top), V(-1, low, top - c)]
        cutter = Part.Face(Part.makePolygon(points + [points[0]])).extrude(V(WIDTH + 2, 0, 0))
        shape = shape.cut(cutter)
    # Flat side ear, with clipped outer corners, gives a grip away from the glue.
    outline = [(21, 35), (30, 35), (32, 37), (32, 53), (30, 55), (21, 55)]
    points = [V(x, y, 0) for x, y in outline]
    ear = Part.Face(Part.makePolygon(points + [points[0]])).extrude(V(0, 0, BACK))
    shape = shape.fuse(ear).removeSplitter()
    if not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError('Each positioning comb must be one valid connected solid')
    return shape


def floor_line_y(z, angle_deg=BAFFLE_ANGLE):
    """Horizontal floor in print YZ, referenced to the first slot's lower wall."""
    if not 0 < angle_deg < 90:
        raise ValueError('Baffle angle must be between 0 and 90 degrees for upward removal')
    angle = math.radians(angle_deg)
    return slot_bounds(0)[0] - (BOTTOM_GAP + math.cos(angle) * (BACK + PROJECTION - z)) / math.sin(angle)


def build_single(angle_deg=BAFFLE_ANGLE):
    shape = build_comb()
    top = BACK + ENGAGEMENT
    # This face becomes horizontal on the 72-degree baffle. Its printed outline
    # shrinks toward +Z, so the foot adds no support or floor-catching undercut.
    points = [V(0, floor_line_y(0, angle_deg), 0), V(0, 1, 0),
              V(0, 1, top), V(0, floor_line_y(top, angle_deg), top)]
    foot = Part.Face(Part.makePolygon(points + [points[0]])).extrude(V(WIDTH, 0, 0))
    shape = shape.fuse(foot).removeSplitter()
    if not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError('Comb and bottom stop must form one valid solid')
    return shape


def installation_placement(x_mm=0, floor_z_mm=0, baffle_bottom_y_mm=0,
                           angle_deg=BAFFLE_ANGLE):
    """Rigid frame: Y uphill along baffle, Z inward, floor is global horizontal."""
    angle = math.radians(angle_deg)
    s, c = math.sin(angle), math.cos(angle)
    board_z = BACK + PROJECTION
    bottom_y = floor_line_y(board_z, angle_deg)
    origin = V(x_mm, baffle_bottom_y_mm - c * bottom_y - s * board_z,
               floor_z_mm - s * bottom_y + c * board_z)
    rotation = App.Rotation(V(-1, 0, 0), V(0, c, s), V(0, s, -c), 'ZXY')
    return App.Placement(origin, rotation)


def wood_fixture(width=FACE_WIDTH):
    """Temporary nominal test fixture in print coordinates; never saved."""
    strips = [Part.makeBox(240, width, PROJECTION,
                          V(-100, slot_bounds(i)[0], BACK))
              for i in range(COUNT)]
    return Part.makeCompound(strips)


def mesh_volume(mesh):
    vertices, triangles = mesh.Topology
    return sum(vertices[a].dot(vertices[b].cross(vertices[c]))
               for a, b, c in triangles) / 6


def verify_installation(shape, angle_deg=BAFFLE_ANGLE):
    placement = installation_placement(angle_deg=angle_deg)
    installed = shape.copy()
    installed.Placement = placement
    floor = Part.makeBox(1000, 1000, 3, V(-500, -500, -3))
    plane = Part.makePlane(1000, 1000, V(-500, -500, 0))
    baffle = Part.makeBox(1000, 150, 2,
                         V(-500, floor_line_y(BACK + PROJECTION, angle_deg), BACK + PROJECTION))
    baffle.Placement = placement
    contact_area = sum(face.common(plane).Area for face in installed.Faces)
    expected_area = WIDTH * (BACK + ENGAGEMENT) / math.sin(math.radians(angle_deg))
    if abs(contact_area - expected_area) > 1e-5:
        raise ValueError('Bottom stop must make full planar contact with horizontal floor')
    if installed.common(floor).Volume > 1e-6 or installed.common(baffle).Volume > 1e-6:
        raise ValueError('Installed jig penetrates floor or baffle')
    wood = wood_fixture()
    wood.Placement = placement
    clearance = wood.optimalBoundingBox(False).ZMin
    if abs(clearance - BOTTOM_GAP) > 1e-6:
        raise ValueError('Lowest rear slat edge must be 6 mm vertically above floor')
    outward = placement.Rotation.multVec(V(0, 0, -1))
    for distance in (0, 0.1, 1, 3, 7, 10, 14):
        moved = installed.copy()
        moved.translate(outward * distance)
        if (moved.common(floor).Volume > 1e-6 or moved.common(baffle).Volume > 1e-6
                or sum(moved.common(solid).Volume for solid in wood.Solids) > 1e-6):
            raise ValueError('Outward removal interferes with wood, floor or baffle')
    return dict(bottom_gap_vertical_mm=clearance, stop_contact_area_mm2=contact_area,
                floor_and_baffle_overlap_mm3=0, normal_removal_clear=True)


def verify_exports(output=OUTPUT):
    expected = build_single()
    doc = App.openDocument(str(Path(output) / (STEM + '.FCStd')))
    try:
        objects = [obj for obj in doc.Objects if obj.TypeId == 'Part::Feature']
        if len(objects) != 1:
            raise ValueError('Saved CAD must contain exactly one jig object')
        saved = objects[0].Shape
        step = Part.Shape()
        step.read(str(Path(output) / (STEM + '.step')))
        for shape in (saved, step):
            if not shape.isValid() or len(shape.Solids) != 1:
                raise ValueError('CAD/STEP must contain one valid solid')
            if max(shape.cut(expected).Volume, expected.cut(shape).Volume) > 1e-6:
                raise ValueError('Saved CAD/STEP differs from generated combs')
        mesh = Mesh.Mesh(str(Path(output) / (STEM + '.stl')))
        volume = mesh_volume(mesh)
        if (not mesh.isSolid() or mesh.countComponents() != 1 or volume <= 0
                or mesh.hasNonManifolds() or mesh.hasSelfIntersections()):
            raise ValueError('STL must contain one closed, positive-volume component')
        if abs(volume - expected.Volume) > 0.05:
            raise ValueError('STL volume differs from CAD')
        return dict(cad_step_readback_match=True, solid_count=1, closed_mesh=True,
                    mesh_components=1, mesh_nonmanifold_edges=False, mesh_self_intersections=False,
                    triangles=mesh.CountFacets, mesh_volume_mm3=volume,
                    installation=verify_installation(saved))
    finally:
        App.closeDocument(doc.Name)


def export(output=OUTPUT):
    if not App.GuiUp:
        raise RuntimeError('Run tools/build-grille-jigs.FCMacro in the FreeCAD GUI')
    import FreeCADGui as Gui

    output = Path(output)
    target = (output / (STEM + '.FCStd')).resolve()
    if any(doc.FileName and Path(doc.FileName).resolve() == target
           for doc in App.listDocuments().values()):
        raise RuntimeError('Close the target FCStd before rebuilding; save manual edits separately')
    if 'GrilleJigsPrint' in App.listDocuments():
        raise RuntimeError('Close GrilleJigsPrint before rebuilding')
    shape = build_single()
    bounds = shape.optimalBoundingBox(False)
    data = dict(units='mm', quantity=1, installation_quantity=2,
                slat_count=COUNT, slat_face_width_mm=FACE_WIDTH,
                slat_projection_mm=PROJECTION, nominal_gap_mm=GAP, surface_pitch_mm=PITCH,
                nominal_array_height_mm=78, slot_width_mm=SLOT_WIDTH,
                slot_total_clearance_mm=SLOT_WIDTH - FACE_WIDTH,
                tooth_engagement_mm=ENGAGEMENT, baffle_clearance_mm=PROJECTION - ENGAGEMENT,
                back_thickness_mm=BACK, slot_mouth_chamfer_mm=MOUTH_CHAMFER,
                single_size_mm=[bounds.XLength, bounds.YLength, bounds.ZLength],
                baffle_angle_deg=BAFFLE_ANGLE, bottom_gap_vertical_mm=BOTTOM_GAP,
                bottom_datum='Lowest slat lower edge at its baffle-facing rear surface; seat against lower slot wall',
                stop_contact_area_mm2=WIDTH * (BACK + ENGAGEMENT) / math.sin(math.radians(BAFFLE_ANGLE)),
                print_orientation='Flat continuous back on bed (Z=0), teeth upward; no supports',
                installation='Foot rests on horizontal bottom panel; teeth toward baffle; seat strips downhill against lower slot walls; pull outward normal to baffle',
                tolerance_note='Nominal 6 mm gaps; 0.3 mm slot clearance permits uphill movement. Seat all strips against lower slot walls to establish the 6 mm bottom datum.',
                assumptions=['Measured wood and printer fit require a dry test',
                             'Keep glue away from both 22 mm wide contact bands',
                             'Comb positions and holding pressure require physical confirmation'],
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output.mkdir(parents=True, exist_ok=True)
    doc = App.newDocument('GrilleJigsPrint')
    try:
        obj = doc.addObject('Part::Feature', 'GrilleJig1')
        obj.Label = '七槽可拆格栅定位夹具 · 竖直 6 mm 贴底挡脚 · 单只'
        obj.Shape = shape
        obj.addProperty('App::PropertyString', 'DesignJSON', 'Design').DesignJSON = json.dumps(data, ensure_ascii=False)
        obj.ViewObject.Visibility = True
        obj.ViewObject.ShapeColor = (0.20, 0.54, 0.73)
        obj.ViewObject.LineColor = (0.08, 0.17, 0.22)
        obj.ViewObject.DisplayMode = 'Flat Lines'
        doc.recompute()
        mesh = MeshPart.meshFromShape(Shape=obj.Shape, LinearDeflection=0.01,
                                      AngularDeflection=0.08, Relative=False)
        mesh.write(str(output / (STEM + '.stl')))
        step_path = output / (STEM + '.step')
        Part.export([obj], str(step_path))
        step_path.write_text('\n'.join(line.rstrip() for line in step_path.read_text().splitlines()) + '\n')
        view = Gui.getDocument(doc.Name).activeView()
        view.stopAnimating()
        view.setAnimationEnabled(False)
        view.viewAxonometric()
        view.fitAll()
        Gui.updateGui()
        view.saveImage(str(output / 'print-preview.png'), 1400, 1100, 'White')
        doc.saveAs(str(target))
    finally:
        App.closeDocument(doc.Name)
    data['validation'] = verify_exports(output)
    data['files_sha256'] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in (target, step_path, output / (STEM + '.stl'))}
    (output / (STEM + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    return data


def render_installation(output=OUTPUT):
    """Temporary inclined baffle and horizontal floor illustrate the stop datum."""
    import FreeCADGui as Gui

    doc = App.newDocument('GrilleJigsTemporaryPreview')
    try:
        floor = doc.addObject('Part::Feature', 'TemporaryBottom')
        floor.Shape = Part.makeBox(250, 65, 3, V(0, -25, -3))
        floor.ViewObject.ShapeColor = (0.43, 0.31, 0.22)
        board = doc.addObject('Part::Feature', 'TemporaryBaffle')
        board.Shape = Part.makeBox(250, 100, 2, V(-250, floor_line_y(BACK + PROJECTION), BACK + PROJECTION))
        board.Placement = installation_placement()
        board.ViewObject.ShapeColor = (0.15, 0.16, 0.17)
        for i in range(COUNT):
            wood = doc.addObject('Part::Feature', 'TemporarySlat%d' % i)
            wood.Shape = Part.makeBox(230, FACE_WIDTH, PROJECTION, V(-240, slot_bounds(i)[0], BACK))
            wood.Placement = installation_placement()
            wood.ViewObject.ShapeColor = (0.68, 0.45, 0.26)
        for i, x in enumerate((60, 220)):
            shape = build_single()
            shape.Placement = installation_placement(x_mm=x)
            jig = doc.addObject('Part::Feature', 'TemporaryJig%d' % i)
            jig.Shape = shape
            jig.ViewObject.ShapeColor = (0.20, 0.54, 0.73)
        doc.recompute()
        view = Gui.getDocument(doc.Name).activeView()
        view.stopAnimating()
        view.setAnimationEnabled(False)
        view.viewAxonometric()
        view.fitAll()
        Gui.updateGui()
        view.saveImage(str(Path(output) / 'installation-preview.png'), 1600, 1000, 'White')
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    export()
    render_installation()
