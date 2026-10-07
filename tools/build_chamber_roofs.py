"""Independent inserted chamber roofs with 45-degree wall fastening and a sealed lap."""
import hashlib
import json
import math
from pathlib import Path
import tempfile

import FreeCAD as App
import Mesh
import MeshPart
import Part

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'cad/chamber-roofs.json'
OUTPUT = ROOT / 'output/3d-print/chamber-roofs'
V = App.Vector
LABELS = {
    'FullrangeLeft': '左全频顶板',
    'FullrangeRight': '右全频顶板',
    'WooferFront': '低音顶板 · 前半',
    'WooferRear': '低音顶板 · 后半',
}
COLORS = [(0.45, 0.68, 0.81), (0.43, 0.73, 0.64),
          (0.83, 0.64, 0.36), (0.92, 0.77, 0.50)]


def load_config():
    return json.loads(CONFIG.read_text())


def bounds(shape):
    box = shape.optimalBoundingBox(False)
    return [box.XLength, box.YLength, box.ZLength]


def mounting_datums(config, thickness):
    """Thin panels move the head seat into a deeper local post, preserving top access."""
    t = config['trial']
    seat_z = thickness - t['head_seat_below_top']
    return dict(post_depth_mm=t['mount_total_height'] - thickness,
                head_seat_z_mm=seat_z, wall_exit_z_mm=seat_z - t['head_seat_inset'])


def validate_config(config):
    m, t = config['measured'], config['trial']
    if config['units'] != 'mm':
        raise ValueError('Units must be mm')
    for section in (m, t):
        for value in section.values():
            values = value if isinstance(value, list) else [value]
            if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0
                       for v in values):
                raise ValueError('Dimensions must be finite and positive')
    if m['satellite_posts_per_side'] != 2 or m['woofer_posts_per_side'] != 4:
        raise ValueError('Expected two satellite and four woofer posts per side')
    if len(m['printer_volume']) != 3:
        raise ValueError('Printer volume needs three dimensions')
    if not m['screw_diameter'] < t['hole_diameter'] < t['head_pocket_diameter']:
        raise ValueError('Screw must pass freely through a post with remaining walls')
    if t['head_pocket_diameter'] <= m['screw_head_diameter']:
        raise ValueError('Head pocket must clear the measured screw head')
    if m['screw_angle_from_vertical_deg'] != 45:
        raise ValueError('This inserted-wall design requires the confirmed 45-degree axis')
    if m['screw_length'] <= t['head_seat_inset'] * math.sqrt(2):
        raise ValueError('Screw cannot reach the vertical wood wall')
    if t['hole_entry_chamfer'] >= min(m['satellite_plate_thickness'], m['woofer_plate_thickness']) / 2:
        raise ValueError('Entry chamfer removes too much plate')
    mouth_half_height = t['hole_diameter'] / math.sqrt(2)
    if t['post_along_edge_width'] <= t['hole_diameter'] + 2 * t['hole_entry_chamfer']:
        raise ValueError('Post needs material beside the angled bore')
    for thickness in (m['satellite_plate_thickness'], m['woofer_plate_thickness']):
        mount = mounting_datums(config, thickness)
        depth, seat_z = mount['post_depth_mm'], mount['head_seat_z_mm']
        if not -depth + mouth_half_height < mount['wall_exit_z_mm'] < -mouth_half_height:
            raise ValueError('Angled bore must exit wholly through the post vertical face')
        # The full head seat must remain backed by the plate/post union, including below Z=0.
        if depth <= t['head_seat_inset'] - seat_z + t['head_pocket_diameter'] / math.sqrt(2):
            raise ValueError('Post diagonal face intersects the full head seat')
        if t['head_seat_inset'] <= t['head_pocket_diameter'] / (2 * math.sqrt(2)):
            raise ValueError('Head seat crosses the vertical wood wall')
        if seat_z + t['head_pocket_diameter'] / (2 * math.sqrt(2)) >= thickness:
            raise ValueError('Head pocket seat extends above the plate')
    for key in ('left', 'right', 'woofer'):
        thickness = m['woofer_plate_thickness'] if key == 'woofer' else m['satellite_plate_thickness']
        depth = mounting_datums(config, thickness)['post_depth_mm']
        head_opening_inner = (t['head_seat_inset'] + t['head_seat_below_top']
                              + t['head_pocket_diameter'] / math.sqrt(2))
        if 2 * max(depth, head_opening_inner) >= m[key + '_width']:
            raise ValueError('Opposite posts do not fit inside the plate')
    if t['satellite_end_inset'] < t['post_along_edge_width'] / 2:
        raise ValueError('Satellite post crosses an end edge')
    if 2 * t['satellite_end_inset'] + t['post_along_edge_width'] >= min(m['left_length'], m['right_length']):
        raise ValueError('Satellite posts overlap')
    start = t['split_y'] - t['lap_length'] / 2
    end = t['split_y'] + t['lap_length'] / 2
    if not 0 < start < end + t['joint_end_clearance'] < m['woofer_length']:
        raise ValueError('Lap must fit inside the woofer plate')
    if t['joint_end_clearance'] >= t['lap_length'] / 2 or m['lap_glue_gap'] >= m['woofer_plate_thickness']:
        raise ValueError('Joint clearance consumes the lap')
    ys = t['woofer_hole_y']
    if len(ys) != 4 or ys != sorted(set(ys)):
        raise ValueError('Four distinct increasing woofer hole positions required')
    r = t['post_along_edge_width'] / 2
    if ys[0] < r or ys[-1] > m['woofer_length'] - r:
        raise ValueError('Woofer post crosses an end edge')
    if any(b - a <= 2 * r for a, b in zip(ys, ys[1:])):
        raise ValueError('Woofer posts overlap')
    if not (ys[1] + r < start and ys[2] - r > end + t['joint_end_clearance']):
        raise ValueError('Each woofer half needs two posts per side outside the lap')


def mount_posts(shape, width, ys, config, thickness):
    m, t = config['measured'], config['trial']
    posts, holes = [], []
    mount = mounting_datums(config, thickness)
    depth, along = mount['post_depth_mm'], t['post_along_edge_width']
    seat_z = mount['head_seat_z_mm']
    for side, sign, wall_x in [('Left', -1, 0), ('Right', 1, width)]:
        for y in ys:
            # 45-degree triangular post: vertical wood-contact face, broad plate root.
            points = [V(wall_x, y-along/2, 0),
                      V(wall_x-sign*depth, y-along/2, 0),
                      V(wall_x, y-along/2, -depth)]
            posts.append(Part.Face(Part.makePolygon(points + [points[0]])).extrude(V(0, along, 0)))
            center = [wall_x-sign*t['head_seat_inset'], y, seat_z]
            axis = [sign/math.sqrt(2), 0, -1/math.sqrt(2)]
            holes.append(dict(side=side, head_seat_center_mm=center, outward_down_axis=axis,
                              wall_entry_mm=[wall_x, y, mount['wall_exit_z_mm']],
                              top_opening_center_mm=[wall_x-sign*(t['head_seat_inset']+t['head_seat_below_top']), y, thickness]))
    shape = shape.multiFuse(posts).removeSplitter()
    for hole in holes:
        center, axis = V(*hole['head_seat_center_mm']), V(*hole['outward_down_axis'])
        bore = Part.makeCylinder(t['hole_diameter'] / 2, m['screw_length'] + 1, center, axis)
        pocket_length = (t['head_seat_below_top'] + t['head_pocket_diameter']) * math.sqrt(2)
        pocket = Part.makeCylinder(t['head_pocket_diameter'] / 2, pocket_length, center, -axis)
        entry = Part.makeCone(t['hole_diameter'] / 2 + t['hole_entry_chamfer'],
                              t['hole_diameter'] / 2, t['hole_entry_chamfer'],
                              center, axis)
        shape = shape.cut(bore).cut(pocket).cut(entry)
    shape = shape.removeSplitter()
    if not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError('Each printable plate must be one valid connected solid')
    return shape, holes


def print_shape(installed):
    """A rigid flip places the flat installed top on the bed; posts face upward."""
    printable = installed.copy()
    printable.rotate(V(), V(1, 0, 0), 180)
    box = printable.optimalBoundingBox(False)
    printable.translate(V(-box.XMin, -box.YMin, -box.ZMin))
    return printable


def build(config=None):
    config = config or load_config()
    validate_config(config)
    m, t = config['measured'], config['trial']
    start = t['split_y'] - t['lap_length'] / 2
    end = t['split_y'] + t['lap_length'] / 2
    end_gap = t['joint_end_clearance']
    glue_gap = m['lap_glue_gap']
    parts = {}
    for name, key in [('FullrangeLeft', 'left'), ('FullrangeRight', 'right')]:
        width, length = m[key + '_width'], m[key + '_length']
        thickness = m['satellite_plate_thickness']
        blank = Part.makeBox(width, length, thickness)
        shape, holes = mount_posts(blank, width,
                                   [t['satellite_end_inset'], length - t['satellite_end_inset']], config, thickness)
        parts[name] = dict(installed=shape, holes=holes, nominal_size_mm=[width, length, thickness])
    width, length = m['woofer_width'], m['woofer_length']
    thickness = m['woofer_plate_thickness']
    half = thickness / 2
    front = Part.makeBox(width, start, thickness).fuse(
        Part.makeBox(width, end - start, half - glue_gap / 2, V(0, start, half + glue_gap / 2)))
    rear = Part.makeBox(width, length - end - end_gap, thickness, V(0, end + end_gap, 0)).fuse(
        Part.makeBox(width, end - start, half - glue_gap / 2, V(0, start + end_gap, 0)))
    for name, blank, ys in [('WooferFront', front, t['woofer_hole_y'][:2]),
                            ('WooferRear', rear, t['woofer_hole_y'][2:])]:
        shape, holes = mount_posts(blank.removeSplitter(), width, ys, config, thickness)
        parts[name] = dict(installed=shape, holes=holes,
                          nominal_size_mm=[width, end if name == 'WooferFront' else length-start-end_gap, thickness])
    for name, data in parts.items():
        data['mounting_datums'] = mounting_datums(config, data['nominal_size_mm'][2])
        data['printable'] = print_shape(data['installed'])
        data['print_size_mm'] = bounds(data['printable'])
        if any(size > limit + 1e-6 for size, limit in zip(data['print_size_mm'], m['printer_volume'])):
            raise ValueError(f'{name} exceeds printer volume')
    if parts['WooferFront']['installed'].common(parts['WooferRear']['installed']).Volume > 1e-6:
        raise ValueError('Woofer lap collides')
    return parts


def mesh_volume(mesh):
    """Use double-precision tetrahedra; Mesh.Volume loses precision on wide plates."""
    vertices, triangles = mesh.Topology
    origin = mesh.BoundBox.Center
    return math.fsum((vertices[a] - origin).dot(
        (vertices[b] - origin).cross(vertices[c] - origin)) / 6 for a, b, c in triangles)


def verify_exports(output, parts):
    """Read every individual file, including closed nonintersecting STL topology."""
    results = {}
    output = Path(output)
    for name, data in parts.items():
        expected = data['printable']
        doc = App.openDocument(str(output / (name + '.FCStd')))
        try:
            saved = doc.getObject(name).Shape
            step = Part.Shape()
            step.read(str(output / (name + '.step')))
            for shape in (saved, step):
                if not shape.isValid() or len(shape.Solids) != 1:
                    raise ValueError(f'{name}: invalid saved solid')
                if max(shape.cut(expected).Volume, expected.cut(shape).Volume) > 1e-5:
                    raise ValueError(f'{name}: saved geometry differs')
            mesh = Mesh.Mesh(str(output / (name + '.stl')))
            volume = mesh_volume(mesh)
            if (not mesh.isSolid() or mesh.countComponents() != 1 or volume <= 0
                    or mesh.hasNonManifolds() or mesh.hasSelfIntersections()):
                raise ValueError(f'{name}: STL must be a closed manifold without self intersections')
            if abs(volume - expected.Volume) > 1:
                raise ValueError(f'{name}: STL volume differs from CAD')
            mesh_size = [mesh.BoundBox.XLength, mesh.BoundBox.YLength, mesh.BoundBox.ZLength]
            if any(abs(a - b) > 1e-4 for a, b in zip(mesh_size, data['print_size_mm'])):
                raise ValueError(f'{name}: STL dimensions differ from CAD')
            results[name] = dict(valid_solid=True, solid_count=1, cad_step_readback_match=True,
                                 closed_mesh=True, mesh_components=1, non_manifold=False,
                                 self_intersections=False, triangles=mesh.CountFacets,
                                 cad_volume_mm3=expected.Volume, mesh_volume_mm3=volume,
                                 print_size_mm=data['print_size_mm'])
        finally:
            App.closeDocument(doc.Name)
    return results


def preview_svg(config):
    """Dimensioned plan and installation sections using the generator's datums."""
    m, t = config['measured'], config['trial']
    sat_bottom = 760 + m['satellite_plate_thickness'] * 10
    sat_depth = mounting_datums(config, m['satellite_plate_thickness'])['post_depth_mm']
    leaf_mm = (m['woofer_plate_thickness'] - m['lap_glue_gap']) / 2
    leaf_px = leaf_mm / m['woofer_plate_thickness'] * 100
    items = ['<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1100" viewBox="0 0 1400 1100">',
             '<rect width="1400" height="1100" fill="#f5f4ef"/>',
             '<g font-family="PingFang SC, sans-serif" fill="#26343d">',
             '<text x="55" y="55" font-size="30" font-weight="bold">三腔顶板 · 实测尺寸 / 独立打印件</text>',
             f'<text x="55" y="90" font-size="18">单位 mm · 全频厚 {m["satellite_plate_thickness"]:g} / 低音厚 {m["woofer_plate_thickness"]:g} · 45° 斜柱与通孔 · 螺钉斜向拧入竖板</text>']
    for key, label, x, y, scale, color in [
            ('left', '左全频', 90, 175, 2.1, '#9dbecd'),
            ('right', '右全频', 450, 175, 2.1, '#9dcabc'),
            ('woofer', '低音 · 前后两件', 930, 160, 1.6, '#dbc091')]:
        width, length = m[key + '_width'], m[key + '_length']
        ys = ([t['satellite_end_inset'], length - t['satellite_end_inset']]
              if key != 'woofer' else t['woofer_hole_y'])
        items.extend([f'<text x="{x}" y="{y-35}" font-size="22" font-weight="bold">{label}</text>',
                      f'<rect x="{x}" y="{y}" width="{width*scale}" height="{length*scale}" fill="{color}" stroke="#364750" stroke-width="2"/>'])
        entry_inset = t['head_seat_inset'] + t['head_seat_below_top']
        for cx in (entry_inset, width - entry_inset):
            for cy in ys:
                items.append(f'<ellipse cx="{x+cx*scale}" cy="{y+cy*scale}" rx="{t["head_pocket_diameter"]*scale/math.sqrt(2)}" ry="{t["head_pocket_diameter"]*scale/2}" fill="#f5f4ef" stroke="#364750"/>')
        items.extend([f'<text x="{x+width*scale/2}" y="{y+length*scale+30}" font-size="19" text-anchor="middle">宽 {width:g}</text>',
                      f'<text x="{x+width*scale+14}" y="{y+length*scale/2}" font-size="18">长 {length:g}</text>',
                      f'<text x="{x}" y="{y-10}" font-size="15">前边 / Y=0</text>'])
        if key == 'woofer':
            for cy in (t['split_y'] - t['lap_length']/2, t['split_y'] + t['lap_length']/2):
                items.append(f'<path d="M{x} {y+cy*scale} h{width*scale}" stroke="#705b37" stroke-dasharray="6 4"/>')
            items.append(f'<text x="{x+32}" y="{y+t["split_y"]*scale-15}" font-size="16">12 mm 台阶搭接区</text>')
    items.extend(['<text x="85" y="480" font-size="19">全频每侧 2 柱；低音每侧 4 柱。</text>',
                  '<text x="85" y="510" font-size="18">顶面沉孔中心距侧边 14；全频距前后端 20。</text>',
                  '<text x="85" y="540" font-size="18">低音孔距前边 Y=22 / 104 / 180 / 262。</text>',
                  '<text x="55" y="685" font-size="23" font-weight="bold">安装剖面 · 斜柱侧面贴竖板内壁</text>',
                  '<rect x="85" y="750" width="100" height="230" fill="#c5ab87" stroke="#705b37"/>',
                  f'<rect x="185" y="760" width="235" height="{m["satellite_plate_thickness"]*10}" fill="#9dbecd" stroke="#364750"/>',
                  f'<path d="M185 {sat_bottom} H{185+sat_depth*10} L185 980 Z" fill="#9dbecd" stroke="#364750"/>',
                  '<path d="M325 760 L270 815" stroke="#f5f4ef" stroke-width="82"/>',
                  '<path d="M270 815 L185 900" stroke="#f5f4ef" stroke-width="40"/>',
                  '<path d="M270 815 L141.3 943.7" stroke="#536770" stroke-width="6"/>',
                  '<text x="440" y="795" font-size="18">顶面开口 → 45° 斜向沉孔</text>',
                  '<text x="440" y="830" font-size="18">头径 Ø7.6 / 沉孔 Ø8.2 / 通孔 Ø4</text>',
                  '<text x="440" y="870" font-size="18">全频斜柱：17 × 12 × 17（试用值）</text>',
                  '<text x="440" y="900" font-size="18">低音斜柱：14 × 12 × 14（试用值）</text>',
                  '<text x="440" y="935" font-size="18">柱侧面贴竖板；螺丝斜着拧入竖板</text>',
                  '<text x="440" y="970" font-size="18">18.2 杆长：名义入木约 6.18</text>',
                  '<text x="760" y="685" font-size="23" font-weight="bold">低音搭接剖面 · 示意放大</text>',
                  f'<path d="M780 775 H1180 V{775+leaf_px} H980 V875 H780 Z" fill="#c9a367" stroke="#705b37" stroke-width="2"/>',
                  f'<path d="M982 {875-leaf_px} H1182 V775 H1340 V875 H982 Z" fill="#e2c994" stroke="#705b37" stroke-width="2"/>',
                  '<path d="M981 875 V826 H1181 V775" fill="none" stroke="#c96348" stroke-width="3"/>',
                  f'<text x="780" y="925" font-size="18">搭接 12；上下叶各 {leaf_mm:g}；搭接面胶缝 {m["lap_glue_gap"]:g}</text>',
                  f'<text x="780" y="955" font-size="18">红线：连续胶层；总厚 {m["woofer_plate_thickness"]:g}；端部台阶间隙 {t["joint_end_clearance"]:g}</text>',
                  '<text x="55" y="1040" font-size="17">柱尺寸、沉孔、孔位及配合间隙为试用设计值；周边和螺钉处也需密封。实物强度和气密待试装。</text>',
                  '</g></svg>'])
    return '\n'.join(items) + '\n'


def style(obj, color):
    obj.ViewObject.Visibility = True
    obj.ViewObject.ShapeColor = color
    obj.ViewObject.LineColor = (0.20, 0.27, 0.30)
    obj.ViewObject.DisplayMode = 'Flat Lines'


def installation_preview(parts, config, destination):
    """Temporary section fixture and screw proxy, never saved into delivered CAD."""
    import FreeCADGui as Gui

    m = config['measured']
    part = parts['FullrangeLeft']
    hole = part['holes'][0]
    center, axis = V(*hole['head_seat_center_mm']), V(*hole['outward_down_axis'])
    screw = Part.makeCylinder(m['screw_diameter'] / 2, m['screw_length'], center, axis).fuse(
        Part.makeCylinder(m['screw_head_diameter'] / 2, 3, center, -axis))
    # The 3 mm head and 10 mm wood are display assumptions, not supplied hardware geometry.
    wall = Part.makeBox(10, 12, 32, V(-10, 14, -18)).cut(screw)
    section = Part.makeBox(45, 6, 32, V(-10, 20, -18))
    doc = App.newDocument('RoofFasteningSection')
    try:
        for name, shape, color in [('RoofSection', part['installed'], COLORS[0]),
                                    ('WoodSection', wall, (0.73, 0.60, 0.42)),
                                    ('ScrewSection', screw, (0.43, 0.46, 0.48))]:
            obj = doc.addObject('Part::Feature', name)
            obj.Shape = shape.common(section)
            style(obj, color)
        doc.recompute()
        view = Gui.getDocument(doc.Name).activeView()
        Gui.updateGui()
        view.setCameraOrientation(App.Rotation(V(1, 0, 0), V(0, 0, 1), V(0, -1, 0), 'ZYX').Q)
        Gui.updateGui()
        view.fitAll()
        view.redraw()
        Gui.updateGui()
        view.saveImage(str(destination), 1300, 900, 'White')
    finally:
        App.closeDocument(doc.Name)


def export(output=OUTPUT):
    if not App.GuiUp:
        raise RuntimeError('Export with build-chamber-roofs.FCMacro in the FreeCAD GUI')
    import FreeCADGui as Gui

    config = load_config()
    parts = build(config)
    output = Path(output)
    targets = {(output / (name + '.FCStd')).resolve() for name in parts}
    targets.add((output / 'Chamber-roofs.FCStd').resolve())
    if any(doc.FileName and Path(doc.FileName).resolve() in targets
           for doc in App.listDocuments().values()):
        raise RuntimeError('Close chamber roof output documents before regeneration; save edits separately')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.chamber-roofs-', dir=output.parent) as temporary:
        staged = Path(temporary)
        for index, (name, data) in enumerate(parts.items()):
            doc = App.newDocument('ChamberRoofPrint')
            try:
                obj = doc.addObject('Part::Feature', name)
                obj.Label = LABELS[name] + ' · 顶面贴床 / 柱朝上'
                obj.Shape = data['printable']
                obj.addProperty('App::PropertyString', 'ParametersJSON', 'Design').ParametersJSON = json.dumps(config, ensure_ascii=False, sort_keys=True)
                style(obj, COLORS[index])
                doc.recompute()
                mesh = MeshPart.meshFromShape(Shape=obj.Shape, LinearDeflection=0.005,
                                              AngularDeflection=0.04, Relative=False)
                mesh.write(str(staged / (name + '.stl')))
                step_path = staged / (name + '.step')
                Part.export([obj], str(step_path))
                step_path.write_text('\n'.join(line.rstrip() for line in step_path.read_text().splitlines()) + '\n')
                view = Gui.getDocument(doc.Name).activeView()
                view.viewAxonometric()
                view.fitAll()
                Gui.updateGui()
                doc.saveAs(str(staged / (name + '.FCStd')))
            finally:
                App.closeDocument(doc.Name)
        validation = verify_exports(staged, parts)
        doc = App.newDocument('ChamberRoofs')
        try:
            for index, (name, data) in enumerate(parts.items()):
                obj = doc.addObject('Part::Feature', name)
                obj.Label = LABELS[name] + ' · 安装方向'
                obj.Shape = data['installed']
                obj.Placement.Base = V([0, 150, 310, 310][index], 0, 0)
                obj.addProperty('App::PropertyString', 'ParametersJSON', 'Design').ParametersJSON = json.dumps(config, ensure_ascii=False, sort_keys=True)
                style(obj, COLORS[index])
            doc.recompute()
            view = Gui.getDocument(doc.Name).activeView()
            view.setCameraOrientation(App.Rotation(V(1, 0, 0), V(0, 0, 1), V(0.5, -1, -2), 'ZYX').Q)
            view.fitAll()
            Gui.updateGui()
            view.saveImage(str(staged / 'model-preview.png'), 1600, 1000, 'White')
            doc.saveAs(str(staged / 'Chamber-roofs.FCStd'))
            view.setCameraOrientation(App.Rotation(V(1, 0, 0), V(0, 0, 1), V(0.5, -1, 2), 'ZYX').Q)
            Gui.updateGui()
            view.fitAll()
            view.redraw()
            Gui.updateGui()
            view.saveImage(str(staged / 'model-top.png'), 1600, 1000, 'White')
            installation_preview(parts, config, staged / 'installation-section.png')
        finally:
            App.closeDocument(doc.Name)
        report = dict(parameters=config, validation=validation,
                      assembled_woofer_size_mm=[config['measured']['woofer_width'], config['measured']['woofer_length'], config['measured']['woofer_plate_thickness']],
                      nominal_wood_engagement_mm=config['measured']['screw_length'] - config['trial']['head_seat_inset'] * math.sqrt(2),
                      maximum_flush_cylindrical_head_height_mm=config['trial']['head_seat_below_top'] * math.sqrt(2) - config['measured']['screw_head_diameter'] / 2,
                      lap_leaf_thickness_mm=(config['measured']['woofer_plate_thickness'] - config['measured']['lap_glue_gap']) / 2,
                      print_orientation='Installed top on bed, downward posts become upward; rigid 180 degree X rotation, never mirror',
                      rear_lap_support_required=True,
                      parts={name: dict(nominal_size_mm=data['nominal_size_mm'],
                                        print_size_mm=data['print_size_mm'],
                                        holes_installed=data['holes'],
                                        mounting_datums=data['mounting_datums'],
                                        post_count=len(data['holes'])) for name, data in parts.items()})
        (staged / 'chamber-roofs.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        (staged / 'dimensions.svg').write_text(preview_svg(config))
        filenames = list(staged.iterdir())
        (staged / 'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n' for path in sorted(filenames)))
        output.mkdir(parents=True, exist_ok=True)
        for path in staged.iterdir():
            path.replace(output / path.name)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    export()
