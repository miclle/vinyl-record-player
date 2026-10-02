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
BRIDGE_CLEARANCE = 8.0  # Trial height above aluminium; tool dimensions unmeasured.
BRIDGE_WIDTH = 3.0
BRIDGE_THICKNESS = 3.0
ANCHOR_WIDTH = 3.0
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

    # Lift both connections off the engraving plane. Only the island post
    # descends inside the enclosed counter; the outer anchor sits beyond the glyph.
    bridges = []
    bridge_notes = []
    for index in (0, 1):
        face = letters.Faces[index]
        inner = [wire for wire in face.Wires if not wire.isSame(face.OuterWire)]
        if len(inner) != 1:
            raise ValueError('Expected one enclosed counter in A and R')
        island = Part.Face(inner[0])
        center = island.CenterOfMass
        island_bounds = island.optimalBoundingBox(False)
        b = face.optimalBoundingBox(False)
        anchor = V(center.x, b.YMax + ANCHOR_WIDTH / 2 + 0.2, 0)
        anchor_foot = Part.makePlane(ANCHOR_WIDTH, ANCHOR_WIDTH,
                                     anchor - V(ANCHOR_WIDTH / 2, ANCHOR_WIDTH / 2, 0))
        if anchor_foot.common(letters).Area > 1e-7:
            raise ValueError('Bridge anchor must not obstruct any letter')
        top = BRIDGE_CLEARANCE + BRIDGE_THICKNESS
        # Use the whole island footprint to strengthen the post without
        # entering the engraving outline. The beam covers its full top face.
        post = island.extrude(V(0, 0, top))
        support = anchor_foot.extrude(V(0, 0, top))
        x, y = center.x - BRIDGE_WIDTH / 2, island_bounds.YMin
        length, breadth = BRIDGE_WIDTH, anchor.y + ANCHOR_WIDTH / 2 - y
        if x > island_bounds.XMin or x + length < island_bounds.XMax:
            raise ValueError('Beam must cover the full island post width')
        beam = Part.makeBox(length, breadth, BRIDGE_THICKNESS, V(x, y, BRIDGE_CLEARANCE))
        bridges.extend((post, support, beam))
        bridge_notes.append(dict(letter=nameplate.TEXT[index], direction='up',
                                 post_area_mm2=island.Area,
                                 post_bounds_xy_mm=[island_bounds.XMin, island_bounds.YMin,
                                                    island_bounds.XMax, island_bounds.YMax],
                                 post_center_mm=[center.x, center.y],
                                 anchor_center_mm=[anchor.x, anchor.y],
                                 beam_bounds_xy_mm=[x, y, x + length, y + breadth]))

    cutters = letters.extrude(V(0, 0, FACE_THICKNESS + 0.2))
    cutters.translate(V(0, 0, -0.1))
    panel = Part.makeBox(width, height, FACE_THICKNESS).cut(cutters)
    # The two free counters are already included in the full-height posts.
    # Do not fuse duplicate curved counter walls into those posts.
    if len(panel.Solids) != 3:
        raise ValueError('Expected outer panel plus two enclosed counter islands')
    panel = max(panel.Solids, key=lambda solid: solid.Volume)
    top_stop = Part.makeBox(width, STOP_THICKNESS, STOP_DEPTH + 0.1,
                            V(0, face_height, -STOP_DEPTH))
    right_stop = Part.makeBox(STOP_THICKNESS, face_height, STOP_DEPTH + 0.1,
                              V(face_width, 0, -STOP_DEPTH))
    installed = panel.multiFuse([top_stop, right_stop] + bridges).removeSplitter()
    if not installed.isValid() or len(installed.Solids) != 1:
        raise ValueError('Stencil must be one connected valid solid, including both counters')

    # Face up: locating stops touch the bed. Panel, islands and beams need supports.
    printable = installed.copy()
    printable.translate(V(0, 0, STOP_DEPTH))
    bounds = printable.optimalBoundingBox(False)
    text_bounds = letters.optimalBoundingBox(False)
    metadata = dict(
        text=nameplate.TEXT, font='Sigmar One', units='mm',
        print_size_mm=[round(value, 6) for value in
                       (bounds.XLength, bounds.YLength, bounds.ZLength)],
        face_thickness_mm=FACE_THICKNESS, stop_thickness_mm=STOP_THICKNESS,
        stop_depth_mm=STOP_DEPTH, bridge_width_mm=BRIDGE_WIDTH,
        bridge_clearance_mm=BRIDGE_CLEARANCE, bridge_thickness_mm=BRIDGE_THICKNESS,
        post_profile='Full enclosed glyph counter extruded vertically',
        anchor_width_mm=ANCHOR_WIDTH,
        bare_fascia_face_mm=[trim['length'], face_height, p['fascia']['thickness']],
        local_fascia_right_mm=face_width, local_fascia_top_mm=face_height,
        local_origin_in_assembly_mm=[plate['left'], 0, trim['bottom']],
        text_bounds_mm=[text_bounds.XMin, text_bounds.YMin,
                        text_bounds.XMax, text_bounds.YMax],
        bridges=bridge_notes,
        print_orientation='Operating face upwards; stops on bed; supports required under panel, islands and beams',
        use='Bare fascia only; continuous engraving plane; raised beams still restrict tool approach',
        tool_fit='Tool tip and shaft clearance require a trial; no depth control',
    )
    return installed, printable, metadata


def preview_svg(installed, metadata):
    """Project the actual solid, including bridges, rather than reusing laser artwork."""
    import TechDraw

    def projection(shape, direction):
        svg = TechDraw.projectToSVG(shape, direction)
        # Apply the page's Y flip and line width once, after projection.
        return svg.replace('transform="scale(1, -1)"', '').replace(
            'stroke-width="1.0"', 'stroke-width="0.15"')

    contact_layer = installed.common(Part.makeBox(120, 40, FACE_THICKNESS))
    front = projection(contact_layer, V(0, 0, 1))
    iso = projection(installed, V(1, -1, 2))
    size = metadata['print_size_mm']
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="900" viewBox="0 0 1200 900">
<rect width="1200" height="900" fill="#f4f5f7"/>
<g fill="#1c2939" font-family="PingFang SC, sans-serif">
<text x="50" y="52" font-size="28" font-weight="bold">Ariel 镂空雕刻定位支架</text>
<text x="50" y="84" font-size="17">Sigmar One｜{size[0]:g} × {size[1]:g} × {size[2]:g} mm｜镂空面板厚 1.2 mm</text>
<text x="50" y="128" font-size="16">贴面层投影（不显示上方横梁）｜A、R 字形连续，岛块由上方立柱连接</text>
</g>
<g transform="translate(50 430) scale(9 -9)">{front}</g>
<g fill="#1c2939" font-family="PingFang SC, sans-serif" font-size="16">
<text x="50" y="480">上沿、右端两道挡边靠住裸铝饰条定位，适配 30 mm 高、5 mm 厚的正面。</text>
<text x="50" y="508">贴面字形连续；横梁下净高 8 mm，刀杆需避让横梁，尺寸待试刻。</text>
<text x="50" y="548">立体视图｜3 × 3 mm 横梁与外侧支柱，内孔轮廓整体延伸为异形柱</text>
</g>
<g transform="translate(140 830) scale(5 -5)">{iso}</g>
<g fill="#1c2939" font-family="PingFang SC, sans-serif" font-size="16">
<text x="670" y="610">STL 操作面朝上，必须添加支撑</text>
<text x="670" y="642">挡边接触热床，面板下方及桥下加支撑。</text>
<text x="670" y="670">A、R 岛块下方也需支撑，去除后检查贴合。</text>
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
        feature.WorkingFace = 'Aluminium contact at Z=5.3; readable from above; supports required'
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
