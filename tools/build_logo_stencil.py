"""One-piece, print-ready Ariel engraving stencil for the bare T fascia."""
import json
from pathlib import Path

import FreeCAD as App
import MeshPart
import Part

import fascia
import nameplate

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/3d-print'
FACE_THICKNESS = 1.2
STOP_THICKNESS = 2.0
STOP_DEPTH = 5.3
BRIDGE_WIDTH = 1.2
V = App.Vector


def build(p, doc):
    """Local X is right, Y is up; Z=0 contacts aluminium, +Z faces the operator."""
    import Draft

    plate = nameplate.dimensions(p)
    trim = fascia.dimensions(p)
    face_width = trim['x'] + trim['length'] - plate['left']
    face_height = p['fascia']['face_height']
    width = face_width + STOP_THICKNESS
    height = face_height + STOP_THICKNESS
    if p['fascia']['thickness'] > STOP_DEPTH:
        raise ValueError('Fascia thickness exceeds the stencil stop depth')

    label = Draft.make_shapestring(nameplate.TEXT, str(nameplate.FONT),
                                   Size=p['fascia']['nameplate']['text_height'])
    try:
        doc.recompute()
        letters = label.Shape.copy()
        if len(letters.Faces) != 5:
            raise ValueError('Expected five Sigmar One letter faces')
        b = letters.optimalBoundingBox(False)
        letters.translate(V((plate['width'] - b.XLength) / 2 - b.XMin,
                            (face_height - b.YLength) / 2 - b.YMin, 0))
    finally:
        doc.removeObject(label.Name)

    # A's island connects upwards, R's to the right, leaving only two touch-up gaps.
    bridges = []
    bridge_notes = []
    for index, direction in ((0, 'up'), (1, 'right')):
        face = letters.Faces[index]
        inner = [wire for wire in face.Wires if not wire.isSame(face.OuterWire)]
        if len(inner) != 1:
            raise ValueError('Expected one enclosed counter in A and R')
        center = Part.Face(inner[0]).CenterOfMass
        b = face.optimalBoundingBox(False)
        if direction == 'up':
            x, y = center.x - BRIDGE_WIDTH / 2, center.y
            length, breadth = BRIDGE_WIDTH, b.YMax - center.y + 0.1
        else:
            x, y = center.x, center.y - BRIDGE_WIDTH / 2
            length, breadth = b.XMax - center.x + 0.1, BRIDGE_WIDTH
        bridges.append(Part.makeBox(length, breadth, FACE_THICKNESS + 0.2,
                                    V(x, y, -0.1)))
        bridge_notes.append(dict(letter=nameplate.TEXT[index], direction=direction,
                                 x_mm=x, y_mm=y, width_mm=length, height_mm=breadth))

    cutters = letters.extrude(V(0, 0, FACE_THICKNESS + 0.2))
    cutters.translate(V(0, 0, -0.1))
    for bridge in bridges:
        cutters = cutters.cut(bridge)
    panel = Part.makeBox(width, height, FACE_THICKNESS).cut(cutters)
    top_stop = Part.makeBox(width, STOP_THICKNESS, STOP_DEPTH + 0.1,
                            V(0, face_height, -STOP_DEPTH))
    right_stop = Part.makeBox(STOP_THICKNESS, face_height, STOP_DEPTH + 0.1,
                              V(face_width, 0, -STOP_DEPTH))
    installed = panel.fuse(top_stop).fuse(right_stop).removeSplitter()
    if not installed.isValid() or len(installed.Solids) != 1:
        raise ValueError('Stencil must be one connected valid solid, including both counters')

    # Put the working face on the bed. This is a rigid rotation, not mirrored lettering.
    printable = installed.copy()
    printable.rotate(V(0, 0, 0), V(1, 0, 0), 180)
    printable.translate(V(0, height, FACE_THICKNESS))
    bounds = printable.optimalBoundingBox(False)
    text_bounds = letters.optimalBoundingBox(False)
    metadata = dict(
        text=nameplate.TEXT, font='Sigmar One', units='mm',
        print_size_mm=[round(value, 6) for value in
                       (bounds.XLength, bounds.YLength, bounds.ZLength)],
        face_thickness_mm=FACE_THICKNESS, stop_thickness_mm=STOP_THICKNESS,
        stop_depth_mm=STOP_DEPTH, bridge_width_mm=BRIDGE_WIDTH,
        bare_fascia_face_mm=[trim['length'], face_height, p['fascia']['thickness']],
        local_fascia_right_mm=face_width, local_fascia_top_mm=face_height,
        local_origin_in_assembly_mm=[plate['left'], 0, trim['bottom']],
        text_bounds_mm=[text_bounds.XMin, text_bounds.YMin,
                        text_bounds.XMax, text_bounds.YMax],
        bridges=bridge_notes,
        print_orientation='Working face at Z=0; stops upwards; no supports',
        use='Bare fascia only, cover/woodwork excluded; bridge gaps require touch-up',
        tool_fit='Tool tip and shaft clearance require a trial; no depth control',
    )
    return installed, printable, metadata


def preview_svg(installed, metadata):
    """Project the actual solid, including bridges, rather than reusing laser artwork."""
    import TechDraw

    def projection(direction):
        svg = TechDraw.projectToSVG(installed, direction)
        # Apply the page's Y flip and line width once, after projection.
        return svg.replace('transform="scale(1, -1)"', '').replace(
            'stroke-width="1.0"', 'stroke-width="0.15"')

    front = projection(V(0, 0, 1))
    iso = projection(V(1, -1, 2))
    size = metadata['print_size_mm']
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="900" viewBox="0 0 1200 900">
<rect width="1200" height="900" fill="#f4f5f7"/>
<g fill="#1c2939" font-family="PingFang SC, sans-serif">
<text x="50" y="52" font-size="28" font-weight="bold">Ariel 镂空雕刻定位支架</text>
<text x="50" y="84" font-size="17">Sigmar One｜{size[0]:g} × {size[1]:g} × {size[2]:g} mm｜镂空面板厚 1.2 mm</text>
<text x="50" y="128" font-size="16">操作面正视｜A、R 内孔通过 1.2 mm 连接桥保留</text>
</g>
<g transform="translate(50 430) scale(9 -9)">{front}</g>
<g fill="#1c2939" font-family="PingFang SC, sans-serif" font-size="16">
<text x="50" y="480">上沿、右端两道挡边靠住裸铝饰条定位，适配 30 mm 高、5 mm 厚的正面。</text>
<text x="50" y="508">取下支架后补磨两处连接桥遮挡的文字；支架不限制雕刻深度。</text>
<text x="50" y="548">立体视图｜挡边伸向铝面背后</text>
</g>
<g transform="translate(140 830) scale(5 -5)">{iso}</g>
<g fill="#1c2939" font-family="PingFang SC, sans-serif" font-size="16">
<text x="670" y="610">STL 已摆好打印姿态，无需支撑</text>
<text x="670" y="642">大平面贴热床，两道挡边朝上。</text>
<text x="670" y="670">操作时从热床接触面看，文字方向正确。</text>
<text x="670" y="698">在饰条安装前加工，或先拆下饰条。</text>
</g>
</svg>'''
    return '\n'.join(line.rstrip() for line in svg.splitlines()) + '\n'


def export(output=OUTPUT):
    # Headless FCStd saving omits GuiDocument.xml and reopens with a hidden provider.
    if not App.GuiUp:
        raise RuntimeError('Export with tools/build-logo-stencil.FCMacro in the FreeCAD GUI')
    import FreeCADGui as Gui

    p = json.loads((ROOT / 'cad/parameters.json').read_text())
    output = Path(output)
    target = (output / 'Ariel-stencil.FCStd').resolve()
    if any(doc.FileName and Path(doc.FileName).resolve() == target
           for doc in App.listDocuments().values()):
        raise RuntimeError('Close Ariel-stencil.FCStd before regenerating it; save edits separately')
    output.mkdir(parents=True, exist_ok=True)
    doc = App.newDocument('ArielStencil')
    try:
        installed, printable, metadata = build(p, doc)
        feature = doc.addObject('Part::Feature', 'ArielStencil')
        feature.Label = 'Ariel 镂空雕刻定位支架（打印姿态）'
        feature.Shape = printable
        feature.addProperty('App::PropertyString', 'WorkingFace', 'Printing')
        feature.WorkingFace = 'Z=0 / build plate side; readable from below'
        feature.ViewObject.Visibility = True
        feature.ViewObject.ShapeColor = (0.72, 0.79, 0.88)
        feature.ViewObject.LineColor = (0.12, 0.16, 0.21)
        feature.ViewObject.DisplayMode = 'Flat Lines'
        doc.recompute()
        mesh = MeshPart.meshFromShape(Shape=printable, LinearDeflection=0.03,
                                      AngularDeflection=0.15, Relative=False)
        if not mesh.isSolid() or mesh.countComponents() != 1:
            raise ValueError('STL must be closed and contain one connected component')
        mesh.write(str(output / 'Ariel-stencil.stl'))
        step_path = output / 'Ariel-stencil.step'
        Part.export([feature], str(step_path))
        step_path.write_text('\n'.join(line.rstrip() for line in
                                      step_path.read_text().splitlines()) + '\n')
        view = Gui.getDocument(doc.Name).activeView()
        view.viewAxonometric()
        view.fitAll()
        doc.saveAs(str(target))
        metadata['validation'] = dict(valid_solid=True, solid_count=1,
                                      closed_mesh=True, mesh_components=1,
                                      triangles=mesh.CountFacets)
        (output / 'Ariel-stencil.json').write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
        (ROOT / 'previews/logo-stencil.svg').write_text(preview_svg(installed, metadata))
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    export()
