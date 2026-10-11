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
    arms = p['horizontal_arms']
    left, right, strip = arms['left_x_mm'], arms['right_x_mm'], arms['strip_height_mm']
    top = arms['top_y_mm']
    bottom = arms['bottom_y_mm']
    if not left < -e < right == 0 or not 0 < strip or not start <= top < top+strip < bottom <= h-strip:
        raise ValueError('Horizontal arms must join the left side of the stepped plate')
    outline = [(0,0),(w,0),(w,h),(0,h),(0,bottom+strip),(left,bottom+strip),
               (left,bottom),(-e,bottom),(-e,top+strip),(left,top+strip),(left,top),(0,top)]
    window = front['mounting']['wood_window']
    x, y, ww, wh = (window[k] for k in ('x_mm', 'y_mm', 'width_mm', 'height_mm'))
    relief = p['pcb_bottom_relief']
    left, right = relief['x_mm'], relief['x_mm'] + relief['width_mm']
    bottom = h - relief['bottom_margin_mm']
    if not x <= left < right <= x+ww or not y+wh < bottom < h:
        raise ValueError('PCB relief must extend below the window and stay inside the outline')
    opening = [(x, y), (x+ww, y), (x+ww, y+wh), (right, y+wh),
               (right, bottom), (left, bottom), (left, y+wh), (x, y+wh)]
    if abs(left-x)<1e-6 and abs(right-x-ww)<1e-6:
        opening = [(x,y),(x+ww,y),(x+ww,bottom),(x,bottom)]
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
    arms = p['horizontal_arms']
    if not rib['flush_with_horizontal_ribs']:
        raise ValueError('Vertical rib must stop flush at horizontal ribs')
    top = arms['top_y_mm']+arms['strip_height_mm']-arms['rib_width_mm']
    bottom = arms['bottom_y_mm']+arms['rib_width_mm']
    return Part.makeBox(width,bottom-top,height,
                        V(-p['left_extension_mm'],front['height_mm']-bottom,p['thickness_mm']))


def arm_rib_shapes(p, front):
    arms = p['horizontal_arms']
    width, rise = arms['rib_width_mm'], arms['rib_height_mm']
    if (arms['direction'] != 'front' or not 0 < width <= arms['strip_height_mm']
            or rise <= 0 or abs(rise+p['thickness_mm']-arms['rib_total_height_including_plate_mm'])>1e-6):
        raise ValueError('Horizontal ribs must rise forwards with total height including the plate')
    if not arms['rib_end_at_left_rib_inner_edge']:
        raise ValueError('Horizontal ribs must stop at the vertical rib inner edge')
    right = -p['left_extension_mm']+p['left_rib']['width_mm']
    length = right-arms['left_x_mm']
    return [Part.makeBox(length,width,rise,V(arms['left_x_mm'],y,p['thickness_mm']))
            for y in (front['height_mm']-arms['top_y_mm']-arms['strip_height_mm'],
                      front['height_mm']-arms['bottom_y_mm']-width)]


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
    shape = shape.fuse(left_rib_shape(p, front))
    for rib in arm_rib_shapes(p, front):
        shape = shape.fuse(rib)
    # Carry the inner corner rounds down to the bed, avoiding a floating gusset.
    for corner in junction_fillets(p):
        x, y, r, direction = corner
        y0 = y if direction == 1 else y-r
        square = prism([(x-r,y0),(x,y0),(x,y0+r),(x-r,y0+r)], h,
                       p['left_rib']['total_height_including_plate_mm'])
        circle = Part.makeCylinder(r, p['left_rib']['total_height_including_plate_mm'],
                                   V(x-r, h-y-direction*r, 0))
        shape = shape.fuse(square.cut(circle))
    # Round the convex rib corners above the 2 mm plate without thinning that plate.
    for x,y,r,direction in outer_junction_fillets(p):
        y0 = y if direction == 1 else y-r
        square = prism([(x-r,y0),(x,y0),(x,y0+r),(x-r,y0+r)], h,
                       p['left_rib']['height_mm'])
        square.translate(V(0,0,t))
        circle = Part.makeCylinder(r,p['left_rib']['height_mm'],
                                   V(x-r,h-y-direction*r,t))
        shape = shape.cut(square.cut(circle))
    shape = shape.removeSplitter()
    if not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError('Backing must be one valid solid')
    return shape


def junction_fillets(p):
    arms = p['horizontal_arms']
    fillets = p['rib_junction_fillets']
    top, bottom = fillets['top_radius_mm'], fillets['bottom_radius_mm']
    if not fillets['extend_through_plate'] or not 0 < top <= 10 or not 0 < bottom <= 10:
        raise ValueError('Junction radii must be positive and supported through the plate')
    return [(-p['left_extension_mm'], arms['top_y_mm']+arms['strip_height_mm'], top, 1),
            (-p['left_extension_mm'], arms['bottom_y_mm'], bottom, -1)]


def outer_junction_fillets(p):
    arms, fillets = p['horizontal_arms'], p['rib_junction_fillets']
    if not fillets['outer_corners']:
        raise ValueError('Both inner and outer junctions must be rounded')
    if max(fillets['top_radius_mm'],fillets['bottom_radius_mm']) > p['left_rib']['width_mm']:
        raise ValueError('Outer corner radii must fit within the rib width')
    x = -p['left_extension_mm']+p['left_rib']['width_mm']
    return [(x,arms['top_y_mm']+arms['strip_height_mm']-arms['rib_width_mm'],
             fillets['top_radius_mm'],1),
            (x,arms['bottom_y_mm']+arms['rib_width_mm'],fillets['bottom_radius_mm'],-1)]


def print_shape(shape, p, front):
    result = shape.copy()
    # Back face stays on the bed; the front lip grows upwards without support.
    result.translate(V(-p["horizontal_arms"]["left_x_mm"], 0, 0))
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
        if installed.common(Part.makeBox(front["width_mm"],front["height_mm"],front["thickness_mm"])).Volume > 1e-6:
            raise ValueError('Backing intersects the flat control panel')
        mesh = Mesh.Mesh(str(output / f'{STEM}.stl'))
        if (not mesh.isSolid() or mesh.countComponents() != 1 or mesh.hasNonManifolds()
                or mesh.hasSelfIntersections() or panel.mesh_volume(mesh) <= 0):
            raise ValueError('Invalid STL topology')
        if abs(panel.mesh_volume(mesh)-expected.Volume) > 0.02:
            raise ValueError('STL volume differs excessively')
        bounds = mesh.BoundBox
        expected_bounds = (0, 0, 0, front['width_mm']-p['horizontal_arms']['left_x_mm'],
                           front['height_mm'], p['left_rib']['total_height_including_plate_mm'])
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
    outline,opening,holes=layout(p,front)
    h=front['height_mm']
    arms=p['horizontal_arms']
    def path(points):
        return 'M '+' L '.join(f'{x:g} {y:g}' for x,y in points)+' Z'
    bores=''.join(f'<circle cx="{v["x_mm"]}" cy="{v["y_mm"]}" r="{v["diameter_mm"]/2}"/>' for v in holes)
    ribs=(f'<rect x="-8" y="33" width="3" height="129"/>'
          f'<rect x="{arms["left_x_mm"]:g}" y="33" width="60" height="3"/>'
          f'<rect x="{arms["left_x_mm"]:g}" y="{arms["bottom_y_mm"]:g}" width="60" height="3"/>')
    rounds = ''.join(f'<path d="M {x-r:g} {y:g} H {x:g} V {y+d*r:g} '
                     f'A {r:g} {r:g} 0 0 {0 if d == 1 else 1} {x-r:g} {y:g} Z"/>'
                     for x,y,r,d in junction_fillets(p))
    ribs += rounds
    ribs += ''.join(f'<path d="M {x-r:g} {y:g} H {x:g} V {y+d*r:g} '
                    f'A {r:g} {r:g} 0 0 {0 if d == 1 else 1} {x-r:g} {y:g} Z" '
                    'fill="#d8e3ea" stroke="none"/>'
                    for x,y,r,d in outer_junction_fillets(p))
    front_face = panel.face_svg(front, panel.load_appearance())
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1000" viewBox="0 0 1200 1000">
<rect width="1200" height="1000" fill="#fafafa"/><g font-family="PingFang SC,sans-serif" fill="#263b49">
<text x="40" y="50" font-size="29" font-weight="600">旋钮面板与底板 · 主体上下等宽 70 mm</text>
<text x="40" y="90" font-size="19">面板 70 × 170 × 3.5 mm · 底板厚 2 mm · 底板外廓 135 × 170 × 12 mm</text>
<text x="40" y="145" font-size="21">底板正面 · 棕色为凸起投影</text><text x="470" y="145" font-size="21">叠放 · 两板固定孔对齐</text>
<g transform="translate(220 205) scale(3)" stroke="#38586e" stroke-width="0.3" fill="white">
<path d="{path(outline)} {path(opening)}" fill="#d8e3ea" fill-rule="evenodd"/>{bores}
<g fill="#b66a39" stroke="#8d4924">{ribs}</g>
<path d="M -65 -5 H 70 M -65 -7 V -3 M 70 -7 V -3" fill="none"/>
<g font-size="4" stroke="none" fill="#263b49"><text x="2.5" y="-8" text-anchor="middle">135</text>
<text x="-30" y="27" text-anchor="middle">65 × 6</text><text x="-30" y="154" text-anchor="middle">65 × 6</text>
<text x="32.5" y="80" text-anchor="middle">59.4 × 146 底板窗口</text><text x="32.5" y="89" text-anchor="middle">X=2.8 / Y=12～158</text>
<text x="-10" y="34" text-anchor="end">Y=30</text>
<text x="2.5" y="173" text-anchor="middle">下边 Y=170</text></g></g>
<g transform="translate(650 205) scale(3)" stroke-width="0.3">
<path d="{path(outline)}" fill="#d8e3ea" stroke="#38586e"/><g fill="#b66a39" stroke="#8d4924">{ribs}</g>
{front_face}</g>
<g font-size="17"><text x="890" y="215">凸起均朝正面：</text><text x="890" y="250">总高 12，含板厚 2。</text><text x="890" y="285">高出板面 10，宽 3。</text>
<text x="890" y="345">上凸条：Y=33～36</text><text x="890" y="380">下凸条：Y=159～162</text><text x="890" y="415">横凸条 X=−65～−5</text>
<text x="890" y="475">左凸条：X=−8～−5</text><text x="890" y="510">Y=33～162</text>
<text x="890" y="570">固定孔 Ø3.5：</text><text x="890" y="605">上排 Y=6</text><text x="890" y="640">下排 Y=164</text><text x="890" y="675">X=9.5 / 60.5</text></g>
<text x="40" y="785" font-size="18">主体上下边均为 X=0～70，与面板对齐；左侧支承区仅在 Y=30～165，上下长条位置保持。</text>
<text x="40" y="830" font-size="18">横竖凸条内外拐角：上方 R3（Ø6）、下方 R1（Ø2）；内圆角补至背面，背面贴热床打印。</text>
<text x="40" y="875" font-size="17">下横边高 12 mm（Y=158～170）；孔中心 Y=164，上下各 6 mm，Ø7 头部上下各留 2.5 mm。</text>
<text x="40" y="920" font-size="17">此为尺寸与叠放示意，文字不属于底板实体，也不是 1:1 纸模板；模型单色黑色。</text>
</g></svg>\n'''


def render_model_preview(view, front, path):
    center = V((front["width_mm"]-65)/2, front["height_mm"]/2, 6)
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
        obj.Label = '旋钮面板底板 · 厚 2 · 三凸条总高 12 / 宽 3 mm'
        obj.Shape = shape
        obj.addProperty('App::PropertyString', 'DesignJSON', 'Design').DesignJSON = json.dumps(
            {'backing': p, 'front': front}, ensure_ascii=False)
        obj.ViewObject.ShapeColor = (0.12, 0.14, 0.16)
        obj.ViewObject.Visibility = True
        doc.recompute()
        mesh = MeshPart.meshFromShape(Shape=print_shape(shape, p, front),
                    LinearDeflection=0.001, AngularDeflection=0.03, Relative=False)
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
                  cad_coordinates=f'X=x, Y={front["height_mm"]:g}-y; plate Z=0..2, ribs Z=2..12; installed translate Z=-2',
                  stl_coordinates=f'X=x{-p["horizontal_arms"]["left_x_mm"]:+g}, Y={front["height_mm"]:g}-y, Z=0..12; rear face on bed, ribs upwards',
                  locating_rib_wood_insertion_mm=max(0,front['back_rim']['height_mm']-p['thickness_mm']),
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
