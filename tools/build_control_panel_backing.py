"""Independent stepped backing plate; all datums follow the existing control panel."""
import hashlib
import json
from pathlib import Path
import sys

import FreeCAD as App
import Mesh
import MeshPart
import Part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_control_panel as panel

PARAMETERS = ROOT / 'cad/control-panel-backing.json'
OUTPUT = ROOT / 'output/3d-print/control-panel-backing'
STEM = 'Control-panel-backing'
V = App.Vector


def load_parameters():
    return json.loads(PARAMETERS.read_text())


def layout(p, front):
    w, h = front['width_mm'], front['height_mm']
    e, start = p['left_extension_mm'], p['extension_start_y_mm']
    if p['thickness_mm'] <= 0 or e <= 0 or not 0 < start < h:
        raise ValueError('Invalid backing thickness or stepped extension')
    outline = [(0, 0), (w, 0), (w, h), (-e, h), (-e, start), (0, start)]
    window = front['mounting']['wood_window']
    x, y, ww, wh = (window[k] for k in ('x_mm', 'y_mm', 'width_mm', 'height_mm'))
    relief = p['pcb_bottom_relief']
    left, right = relief['x_mm'], relief['x_mm'] + relief['width_mm']
    bottom = h - relief['bottom_margin_mm']
    if not x < left < right < x+ww or not y+wh < bottom < h:
        raise ValueError('PCB relief must extend below the window and stay inside the outline')
    opening = [(x, y), (x+ww, y), (x+ww, y+wh), (right, y+wh),
               (right, bottom), (left, bottom), (left, y+wh), (x, y+wh)]
    holes = [dict(hole) for hole in front['holes'] if hole['role'] == 'mounting']
    return outline, opening, holes


def prism(points, h, t):
    vertices = [V(x, h-y, 0) for x, y in points]
    return Part.Face(Part.makePolygon(vertices + [vertices[0]])).extrude(V(0, 0, t))


def left_rib_shape(p, front):
    rib = p["left_rib"]
    width, height = rib["width_mm"], rib["height_mm"]
    if abs(rib["total_height_including_plate_mm"] - height - p["thickness_mm"]) > 1e-6:
        raise ValueError("Left rib total height must include plate thickness")
    if rib["direction"] != "front" or not 0 < width <= p["left_extension_mm"] or height <= 0:
        raise ValueError("Left rib must rise forwards within the stepped extension")
    return Part.makeBox(width, front["height_mm"]-p["extension_start_y_mm"], height,
                        V(-p["left_extension_mm"], 0, p["thickness_mm"]))


def build(p, front):
    outline, opening, holes = layout(p, front)
    h, t = front['height_mm'], p['thickness_mm']
    shape = prism(outline, h, t).cut(prism(opening, h, t))
    for hole in holes:
        shape = shape.cut(Part.makeCylinder(hole['diameter_mm']/2, t+2,
                         V(hole['x_mm'], h-hole['y_mm'], -1)))
        # Leave material around the complete screw-head footprint.
        head = Part.makeCylinder(front['mounting']['screw_head_diameter_mm']/2, t,
                                V(hole['x_mm'], h-hole['y_mm'], 0))
        bore = Part.makeCylinder(hole['diameter_mm']/2, t,
                                V(hole['x_mm'], h-hole['y_mm'], 0))
        if head.cut(bore).cut(shape).Volume > 1e-6:
            raise ValueError('Backing must retain material beneath each screw head')
    shape = shape.fuse(left_rib_shape(p, front)).removeSplitter()
    if not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError('Backing must be one valid solid')
    return shape


def print_shape(shape, p, front):
    result = shape.copy()
    # Back face stays on the bed; the front lip grows upwards without support.
    result.translate(V(p["left_extension_mm"], 0, 0))
    return result


def verify_exports(output, expected, p, front):
    doc = App.openDocument(str(output / f'{STEM}.FCStd'))
    try:
        if json.loads(doc.Backing.DesignJSON) != {'backing': p, 'front': front}:
            raise ValueError('Saved parameter snapshot differs')
        step = Part.Shape()
        step.read(str(output / f'{STEM}.step'))
        for shape in (doc.Backing.Shape, step):
            if not shape.isValid() or len(shape.Solids) != 1:
                raise ValueError('Saved backing is not one valid solid')
            if shape.cut(expected).Volume + expected.cut(shape).Volume > 1e-6:
                raise ValueError('Saved geometry differs from expected solid')
        installed = doc.Backing.Shape.copy()
        installed.translate(V(0, 0, -p['thickness_mm']))
        if installed.common(panel.rim_shape(front)).Volume > 1e-6:
            raise ValueError('Backing intersects the rear locating ribs')
        mesh = Mesh.Mesh(str(output / f'{STEM}.stl'))
        if (not mesh.isSolid() or mesh.countComponents() != 1 or mesh.hasNonManifolds()
                or mesh.hasSelfIntersections() or panel.mesh_volume(mesh) <= 0):
            raise ValueError('Invalid STL topology')
        if abs(panel.mesh_volume(mesh)-expected.Volume) > 0.02:
            raise ValueError('STL volume differs excessively')
        bounds = mesh.BoundBox
        expected_bounds = (0, 0, 0, front['width_mm']+p['left_extension_mm'],
                           front['height_mm'], p['thickness_mm']+p['left_rib']['height_mm'])
        actual_bounds = (bounds.XMin, bounds.YMin, bounds.ZMin,
                         bounds.XLength, bounds.YLength, bounds.ZLength)
        if any(abs(a-b)>1e-5 for a,b in zip(actual_bounds, expected_bounds)):
            raise ValueError('Incorrect STL print bounds')
        return dict(passed=True, valid_solid=True, solid_count=1,
                    mounting_hole_count=4, saved_cad_step_match=True,
                    rear_rib_intersection_mm3=0, front_left_rib_height_mm=p["left_rib"]["height_mm"],
                    front_left_rib_width_mm=p["left_rib"]["width_mm"],
                    total_print_thickness_mm=p["thickness_mm"]+p["left_rib"]["height_mm"],
                    closed_mesh=True, mesh_components=1,
                    mesh_nonmanifold_edges=False, mesh_self_intersections=False,
                    volume_mm3=expected.Volume, mesh_volume_mm3=panel.mesh_volume(mesh),
                    triangles=mesh.CountFacets)
    finally:
        App.closeDocument(doc.Name)


def preview_svg(p, front):
    outline, opening, holes = layout(p, front)
    def path(points):
        return 'M ' + ' L '.join(f'{x:g} {y:g}' for x,y in points) + ' Z'
    bores = ''.join(f'<circle cx="{h["x_mm"]}" cy="{h["y_mm"]}" r="{h["diameter_mm"]/2}"/>' for h in holes)
    function_holes = ''.join(f'<circle cx="{h["x_mm"]}" cy="{h["y_mm"]}" r="{h["diameter_mm"]/2}"/>'
                            for h in front['holes'] if h['role'] != 'mounting')
    lip = f'<rect x="{-p["left_extension_mm"]}" y="{p["extension_start_y_mm"]}" width="{p["left_rib"]["width_mm"]}" height="{front["height_mm"]-p["extension_start_y_mm"]}" fill="#b66a39" stroke="#8d4924"/>'
    shape = f'<path d="{path(outline)} {path(opening)}" fill-rule="evenodd" fill="#d8e3ea"/>{bores}'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="980" viewBox="0 0 1200 980">
<rect width="1200" height="980" fill="#fafafa"/><g font-family="PingFang SC,sans-serif" fill="#263b49">
<text x="48" y="56" font-size="29" font-weight="600">旋钮面板底板 · 左侧阶梯加宽 8 mm</text>
<text x="48" y="98" font-size="19">底板厚 2 mm · 左凸条总高 8 / 宽 3 mm · 外廓 73 × 160 × 8 mm</text>
<text x="48" y="150" font-size="21">底板开孔 · 沿用原面板坐标</text>
<g transform="translate(90 195) scale(3.8)" stroke="#38586e" stroke-width="0.25" fill="white">{shape}{lip}
<path d="M -8 30 H 65 M 0 0 V 160" stroke-dasharray="1.5 1" stroke="#8195a2"/>
<g fill="#263b49" stroke="none" font-size="3.2"><text x="32.5" y="-5" text-anchor="middle">65</text>
<text x="28.5" y="167" text-anchor="middle">73</text><text x="-12" y="30" text-anchor="end">Y=30</text>
<text x="32.5" y="75" text-anchor="middle">主窗口 59.4 × 136</text>
<text x="32.5" y="85" text-anchor="middle">X=2.8 / Y=12</text>
<text x="32.5" y="152.8" font-size="2.6" text-anchor="middle">下方避让口 36 × 10</text></g></g>
<text x="510" y="150" font-size="21">叠放示意 · 正面投影</text>
<g transform="translate(550 195) scale(3.8)" stroke-width="0.25">
<path d="{path(outline)}" fill="#d8e3ea" stroke="#38586e"/>
{lip}<rect width="65" height="160" fill="#262a2d" stroke="#111"/>
<g stroke="#fafafa" fill="#fafafa">{bores}{function_holes}</g>
<path d="M 3.1 12.3 V 147.7 M 61.9 12.3 V 147.7" fill="none" stroke="#e19c52" stroke-dasharray="1.5 1"/>
<g fill="white" font-size="3.5"><text x="10" y="51.5">VOLUME</text><text x="10" y="73.5">TREBLE</text>
<text x="10" y="95.5">BASS</text><text x="10" y="113.5">POWER</text><text x="32.5" y="141" text-anchor="middle" font-size="7">Ariel</text></g></g>
<g font-size="17"><text x="880" y="215">四孔 Ø3.5，位置不变：</text><text x="880" y="250">(9.5, 6) / (55.5, 6)</text>
<text x="880" y="285">(9.5, 154) / (55.5, 154)</text><text x="880" y="350">灰蓝：新增底板；棕：凸条</text>
<text x="880" y="385">黑色：原旋钮面板</text><text x="880" y="420">橙虚线：背面定位条</text>
<text x="880" y="480">侧面叠放：</text><text x="880" y="515">旋钮面板 3.5 mm</text><text x="880" y="550">底板 2 mm</text><text x="880" y="585">木板 10 mm</text>
<text x="880" y="650">凸条朝正面，净高 6 mm。</text><text x="880" y="685">X=−8…−5，Y=30…160。</text>
<text x="880" y="730">原定位条进入木板 8 mm。</text></g>
<text x="48" y="872" font-size="18">PCB 下方避让：X=14.5…50.5，Y=148…158；下排孔保留完整 Ø7 螺丝头承压范围。</text>
<text x="48" y="910" font-size="17">PCB 下缘 Y=157 有 1 mm 名义余量；实际板宽、元件和木板原窗口需试装核对。</text>
<text x="48" y="947" font-size="17">示意文字仅用于识别；新增底板为无文字的单色平板。STL：73 × 160 × 8 mm，底板背面贴热床。</text>
</g></svg>\n'''


def render_model_preview(view, front, path):
    center = V((front["width_mm"]-8)/2, front["height_mm"]/2, 4)
    direction = V(1, -1, 1)
    direction.normalize()
    distance = 2*front["height_mm"]
    position = center+direction*distance
    rotation = App.Rotation(V(0, 0, 1), direction)
    axis = rotation.Axis
    view.setCamera(f"""#Inventor V2.1 ascii
OrthographicCamera {{
  position {position.x} {position.y} {position.z}
  orientation {axis.x} {axis.y} {axis.z} {rotation.Angle}
  nearDistance 1
  farDistance {10*front["height_mm"]}
  focalDistance {distance}
  height {1.2*front["height_mm"]}
}}
""")
    view.saveImage(str(path),1000,1200,'White')


def export(output=OUTPUT):
    if not App.GuiUp:
        raise RuntimeError('Use build-control-panel-backing.FCMacro in FreeCAD GUI')
    import FreeCADGui as Gui
    output = Path(output)
    target = (output / f'{STEM}.FCStd').resolve()
    if any(d.FileName and Path(d.FileName).resolve() == target for d in App.listDocuments().values()):
        raise RuntimeError('Close the backing document before rebuilding; save manual edits separately')
    p, front = load_parameters(), panel.load_parameters()
    shape = build(p, front)
    output.mkdir(parents=True, exist_ok=True)
    original_paths = [panel.PARAMETERS, ROOT / 'cad/record-player.FCStd']
    original_paths += [panel.OUTPUT / f'Control-panel.{ext}' for ext in ('FCStd', 'step', 'stl')]
    original_hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in original_paths if path.exists()}
    doc = App.newDocument('ControlPanelBackingPrint')
    try:
        obj = doc.addObject('Part::Feature', 'Backing')
        obj.Label = '旋钮面板底板 · 厚 2 · 左凸条总高 8 / 宽 3 mm'
        obj.Shape = shape
        obj.addProperty('App::PropertyString', 'DesignJSON', 'Design').DesignJSON = json.dumps(
            {'backing': p, 'front': front}, ensure_ascii=False)
        obj.ViewObject.ShapeColor = (0.12, 0.14, 0.16)
        obj.ViewObject.Visibility = True
        doc.recompute()
        mesh = MeshPart.meshFromShape(Shape=print_shape(shape, p, front),
                    LinearDeflection=0.003, AngularDeflection=0.06, Relative=False)
        mesh.write(str(output / f'{STEM}.stl'))
        Part.export([obj], str(output / f'{STEM}.step'))
        step_path = output / f'{STEM}.step'
        step_path.write_text('\n'.join(line.rstrip() for line in step_path.read_text().splitlines())+'\n')
        view = Gui.getDocument(doc.Name).activeView()
        view.viewAxonometric()
        view.fitAll()
        Gui.updateGui()
        doc.saveAs(str(target))
        render_model_preview(view, front, ROOT / "previews/control-panel-backing-model.png")
    finally:
        App.closeDocument(doc.Name)
    unchanged = all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                    for name, digest in original_hashes.items())
    if not unchanged:
        raise ValueError('Original panel or assembly changed during independent export')
    outline, opening, holes = layout(p, front)
    report = dict(parameters=p, front_parameters=front, outline_front_xy_mm=outline,
                  opening_front_xy_mm=opening, mounting_holes=holes,
                  cad_coordinates='X=x, Y=160-y; plate Z=0..2, left rib Z=2..8; installed translate Z=-2',
                  stl_coordinates='X=x+8, Y=160-y, Z=0..8; backing rear face on bed, rib facing upwards',
                  locating_rib_wood_insertion_mm=front['back_rim']['height_mm']-p['thickness_mm'],
                  pcb_width_fit_confirmed=False, wood_window_fit_changed=False,
                  original_files_unchanged=unchanged, original_sha256=original_hashes,
                  validation=verify_exports(output, shape, p, front))
    report['sha256'] = {f'{STEM}.{ext}': hashlib.sha256((output / f'{STEM}.{ext}').read_bytes()).hexdigest()
                        for ext in ('FCStd', 'step', 'stl')}
    report['verification_sources_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        for name in ('tools/build_control_panel_backing.py', 'tools/build_control_panel.py',
                     'tests/test_control_panel_backing.py', 'cad/control-panel-backing.json',
                     'cad/control-panel.json')}
    (output / f'{STEM}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    (ROOT / 'previews/control-panel-backing.svg').write_text(preview_svg(p, front))
    print(json.dumps(report['validation'], indent=2))


if __name__ == '__main__':
    export()
